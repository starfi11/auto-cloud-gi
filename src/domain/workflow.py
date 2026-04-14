from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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


@dataclass(frozen=True)
class StatePlan:
    initial_state: str
    terminal_states: list[str]
    nodes: list[StateNode]
    max_ticks: int = 200

    def node_for(self, state: str) -> StateNode | None:
        for node in self.nodes:
            if node.state == state:
                return node
        return None


@dataclass(frozen=True)
class WorkflowPlan:
    profile: str
    game: str
    scenario: str
    mode: str = "state_driven"
    state_plan: StatePlan | None = None
    steps: list[WorkflowStep] = field(default_factory=list)

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

        return WorkflowPlan(
            profile=str(payload.get("profile", "")),
            game=str(payload.get("game", "")),
            scenario=str(payload.get("scenario", "")),
            mode=str(payload.get("mode", "linear" if state_plan is None else "state_driven")),
            state_plan=state_plan,
            steps=steps,
        )
