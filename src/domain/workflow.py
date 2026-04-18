from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.domain.blackboard import (
    Blackboard,
    Guard,
    evaluate_guard,
    guard_from_dict,
    guard_to_dict,
)
from src.domain.scenario import ScenarioSpec


@dataclass(frozen=True)
class WorkflowStep:
    name: str
    kind: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionIntent:
    name: str
    kind: str
    params: dict[str, Any] = field(default_factory=dict)
    max_retries: int = 0
    backoff_seconds: float = 0.2
    controller_id: str | None = None
    required_context: str | None = None

    def to_step(self) -> WorkflowStep:
        merged = dict(self.params)
        merged.setdefault("max_retries", self.max_retries)
        merged.setdefault("backoff_seconds", self.backoff_seconds)
        if self.controller_id:
            merged.setdefault("controller_id", self.controller_id)
        if self.required_context:
            merged.setdefault("required_context", self.required_context)
        return WorkflowStep(name=self.name, kind=self.kind, params=merged)


@dataclass(frozen=True)
class StateNode:
    state: str
    action: ActionIntent | None = None
    next_state: str | None = None
    wait_seconds: float = 0.2
    stable_ticks: int = 1
    recognition: dict[str, Any] = field(default_factory=dict)
    controller_id: str | None = None
    context_id: str | None = None
    # Legal successor states for narrow-scan observation sync.
    # None  -> hub/broad-scan (estimator evaluates every node in the plan).
    # list  -> narrow scan restricted to these successors + self.
    expected_next: tuple[str, ...] | None = None
    # Optional predicate over the run blackboard. When multiple nodes
    # share the same ``state`` name, ``StatePlan.node_for`` picks the
    # first one whose guard passes — the mechanism behind "same screen,
    # different action depending on current_goal/counter/phase".
    guard: Guard | None = None
    # Recoverability class. When a relocalize/retry attempt fails, the
    # executor uses this to decide how aggressively to recover:
    #   safe_reentry  -> re-execute the node's action freely (idempotent)
    #   transient     -> retry a few times, then fall back to broad scan
    #   destructive   -> escalate to L5 interrupt immediately; the node
    #                    has side effects we cannot safely repeat
    # Unspecified (default ``transient``) is safe for the common case.
    recoverability: str = "transient"


@dataclass(frozen=True)
class StatePlan:
    initial_state: str
    terminal_states: list[str]
    nodes: list[StateNode]
    max_ticks: int = 200

    def node_for(
        self,
        state: str,
        blackboard: Blackboard | None = None,
    ) -> StateNode | None:
        """Return the first node matching ``state`` whose guard passes.

        Back-compatible: legacy callers omit ``blackboard`` and get the
        first same-named node (unguarded nodes always pass, so profiles
        without guards behave exactly as before).
        """
        for node in self.nodes:
            if node.state != state:
                continue
            if evaluate_guard(node.guard, blackboard):
                return node
        return None

    def validate_expected_next(self) -> list[str]:
        """Return a list of validation errors. Empty list means ok.

        Checks:
          - every state in any expected_next exists in the plan or is terminal
          - every node.next_state (if set) appears in that node's expected_next
            (unless expected_next is None, meaning broad scan)
        """
        known = {n.state for n in self.nodes} | set(self.terminal_states)
        errors: list[str] = []
        for node in self.nodes:
            if node.expected_next is None:
                continue
            for succ in node.expected_next:
                if succ not in known:
                    errors.append(f"{node.state}.expected_next references unknown state {succ!r}")
            if node.next_state and node.next_state not in node.expected_next:
                errors.append(
                    f"{node.state}.next_state={node.next_state!r} not in expected_next {list(node.expected_next)}"
                )
        return errors


@dataclass(frozen=True)
class WorkflowPlan:
    profile: str
    game: str
    scenario: str
    mode: str = "state_driven"
    state_plan: StatePlan | None = None
    steps: list[WorkflowStep] = field(default_factory=list)
    scenario_spec: ScenarioSpec | None = None

    def action_steps_from_state_plan(self) -> list[WorkflowStep]:
        """Derive WorkflowSteps from the state plan's action-bearing nodes.

        Lets consumers that previously read ``plan.steps`` as "the list of
        executable steps" keep working even when a state_driven profile
        stops hand-maintaining a parallel ``steps`` list. Preserves state
        node order. Returns [] when there's no state plan.
        """
        if self.state_plan is None:
            return []
        return [
            node.action.to_step()
            for node in self.state_plan.nodes
            if node.action is not None
        ]

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "profile": self.profile,
            "game": self.game,
            "scenario": self.scenario,
            "mode": self.mode,
            "steps": [
                {
                    "name": s.name,
                    "kind": s.kind,
                    "params": s.params,
                }
                for s in self.steps
            ],
        }
        if self.scenario_spec is not None:
            payload["scenario_spec"] = self.scenario_spec.to_dict()
        if self.state_plan is not None:
            payload["state_plan"] = {
                "initial_state": self.state_plan.initial_state,
                "terminal_states": self.state_plan.terminal_states,
                "max_ticks": self.state_plan.max_ticks,
                "nodes": [
                    {
                        "state": n.state,
                        "next_state": n.next_state,
                        "wait_seconds": n.wait_seconds,
                        "stable_ticks": n.stable_ticks,
                        "recognition": n.recognition,
                        "controller_id": n.controller_id,
                        "context_id": n.context_id,
                        "expected_next": list(n.expected_next) if n.expected_next is not None else None,
                        "guard": guard_to_dict(n.guard),
                        "recoverability": n.recoverability,
                        "action": (
                            {
                                "name": n.action.name,
                                "kind": n.action.kind,
                                "params": n.action.params,
                                "max_retries": n.action.max_retries,
                                "backoff_seconds": n.action.backoff_seconds,
                                "controller_id": n.action.controller_id,
                                "required_context": n.action.required_context,
                            }
                            if n.action is not None
                            else None
                        ),
                    }
                    for n in self.state_plan.nodes
                ],
            }
        return payload

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> WorkflowPlan:
        steps = [
            WorkflowStep(name=s["name"], kind=s["kind"], params=s.get("params", {}))
            for s in payload.get("steps", [])
            if isinstance(s, dict) and "name" in s and "kind" in s
        ]

        raw_state_plan = payload.get("state_plan")
        state_plan: StatePlan | None = None
        if isinstance(raw_state_plan, dict):
            nodes: list[StateNode] = []
            for raw_node in raw_state_plan.get("nodes", []):
                if not isinstance(raw_node, dict):
                    continue
                state = raw_node.get("state")
                if not isinstance(state, str) or not state:
                    continue
                raw_action = raw_node.get("action")
                action: ActionIntent | None = None
                if isinstance(raw_action, dict) and "name" in raw_action and "kind" in raw_action:
                    action = ActionIntent(
                        name=str(raw_action["name"]),
                        kind=str(raw_action["kind"]),
                        params=dict(raw_action.get("params", {})),
                        max_retries=int(raw_action.get("max_retries", 0)),
                        backoff_seconds=float(raw_action.get("backoff_seconds", 0.2)),
                        controller_id=(
                            str(raw_action["controller_id"])
                            if raw_action.get("controller_id") is not None
                            else None
                        ),
                        required_context=(
                            str(raw_action["required_context"])
                            if raw_action.get("required_context") is not None
                            else None
                        ),
                    )
                raw_expected = raw_node.get("expected_next")
                if raw_expected is None:
                    expected_next: tuple[str, ...] | None = None
                elif isinstance(raw_expected, (list, tuple)):
                    expected_next = tuple(
                        str(s) for s in raw_expected if isinstance(s, str) and s
                    )
                else:
                    expected_next = None
                raw_guard = raw_node.get("guard")
                guard = guard_from_dict(raw_guard) if isinstance(raw_guard, dict) else None
                nodes.append(
                    StateNode(
                        state=state,
                        action=action,
                        next_state=(str(raw_node["next_state"]) if raw_node.get("next_state") is not None else None),
                        wait_seconds=float(raw_node.get("wait_seconds", 0.2)),
                        stable_ticks=max(1, int(raw_node.get("stable_ticks", 1))),
                        recognition=(
                            dict(raw_node.get("recognition", {}))
                            if isinstance(raw_node.get("recognition"), dict)
                            else {}
                        ),
                        controller_id=(str(raw_node["controller_id"]) if raw_node.get("controller_id") is not None else None),
                        context_id=(str(raw_node["context_id"]) if raw_node.get("context_id") is not None else None),
                        expected_next=expected_next,
                        guard=guard,
                        recoverability=str(raw_node.get("recoverability", "transient")),
                    )
                )

            initial_state = str(raw_state_plan.get("initial_state", "BOOTSTRAP"))
            terminal_states = [str(v) for v in raw_state_plan.get("terminal_states", []) if isinstance(v, str)]
            state_plan = StatePlan(
                initial_state=initial_state,
                terminal_states=terminal_states,
                nodes=nodes,
                max_ticks=int(raw_state_plan.get("max_ticks", 200)),
            )

        raw_scenario_spec = payload.get("scenario_spec")
        scenario_spec: ScenarioSpec | None = None
        if isinstance(raw_scenario_spec, dict):
            scenario_spec = ScenarioSpec.from_dict(raw_scenario_spec)

        return WorkflowPlan(
            profile=str(payload.get("profile", "")),
            game=str(payload.get("game", "")),
            scenario=str(payload.get("scenario", "")),
            mode=str(payload.get("mode", "linear" if state_plan is None else "state_driven")),
            state_plan=state_plan,
            steps=steps,
            scenario_spec=scenario_spec,
        )
