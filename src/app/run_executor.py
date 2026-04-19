from __future__ import annotations

import os
from time import perf_counter, sleep
from typing import Callable, Any, Protocol

from src.domain.scenario import advance_scenario
from src.domain.stages import Stage
from src.domain.state_kernel import PolicyDecision
from src.domain.workflow import WorkflowPlan, WorkflowStep
from src.kernel.context_store import RunContext
from src.kernel.context_manager import ContextManager
from src.kernel.checkpoint_store import CheckpointStore
from src.kernel.exception_router import InterruptError
from src.kernel.resource_arbiter import ResourceArbiter
from src.infra.log_manager import LogManager
from src.infra.diagnostics import classify_failure
from src.domain.recovery import RecoveryDirective
from src.ports.policy_engine_port import PolicyEnginePort
from src.ports.ai_recovery_planner_port import AiRecoveryPlannerPort
from src.ports.recovery_strategy_port import RecoveryStrategyPort
from src.ports.state_estimator_port import StateEstimatorPort


SignalGetter = Callable[[str], tuple[bool, str]]


class StepExecutor(Protocol):
    def execute(self, step: WorkflowStep, context: RunContext) -> dict[str, Any]:
        ...


class RunExecutor:
    STEP_STAGE_MAP: dict[str, Stage] = {
        "game.launch": Stage.START_CLOUD_GI,
        "game.queue.enter": Stage.ENTER_QUEUE,
        "game.wait.scene": Stage.WAIT_GAME_READY,
        "game.kongyue.claim": Stage.WAIT_GAME_READY,
        "assistant.launch": Stage.START_AND_DRIVE_BTGI,
        "assistant.drive": Stage.MONITOR_AND_GUARD,
        "system.collect": Stage.COLLECT_RESULT,
    }

    def __init__(
        self,
        logs: LogManager,
        checkpoints: CheckpointStore,
        runtime: StepExecutor,
        interrupt_check: SignalGetter | None = None,
        risk_check: SignalGetter | None = None,
        state_estimator: StateEstimatorPort | None = None,
        policy_engine: PolicyEnginePort | None = None,
        context_manager: ContextManager | None = None,
        recovery_strategy: RecoveryStrategyPort | None = None,
        resource_arbiter: ResourceArbiter | None = None,
        ai_recovery_planner: AiRecoveryPlannerPort | None = None,
    ) -> None:
        self._logs = logs
        self._checkpoints = checkpoints
        self._runtime = runtime
        self._interrupt_check = interrupt_check
        self._risk_check = risk_check
        self._state_estimator = state_estimator
        self._policy_engine = policy_engine
        self._context_manager = context_manager
        self._recovery_strategy = recovery_strategy
        self._resource_arbiter = resource_arbiter
        self._ai_recovery_planner = ai_recovery_planner

    def execute(self, context: RunContext, plan: WorkflowPlan) -> None:
        if self._context_manager is not None:
            self._context_manager.ensure_initialized(context)
        if plan.mode == "state_driven" and plan.state_plan is not None:
            self._execute_state_driven(context, plan)
            return
        self._execute_linear(context, plan)

    def _execute_linear(self, context: RunContext, plan: WorkflowPlan) -> None:
        self._transition(context, str(Stage.LOAD_POLICY), reason="workflow_plan_ready")

        for step in plan.steps:
            self._check_preempt(context)
            stage = self.STEP_STAGE_MAP.get(step.kind)
            if stage:
                self._transition(context, str(stage), reason=f"step:{step.name}")
            self._run_step(context, step)

        self._check_preempt(context)
        self._transition(context, str(Stage.NOTIFY_AND_ARCHIVE), reason="steps_completed")
        self._transition(context, str(Stage.FINISH), reason="run_completed")

    def _execute_state_driven(self, context: RunContext, plan: WorkflowPlan) -> None:
        if self._state_estimator is None or self._policy_engine is None:
            raise RuntimeError("state_driven mode requires state_estimator and policy_engine")

        state_plan = plan.state_plan
        if state_plan is None:
            raise RuntimeError("state_driven mode missing state_plan")

        self._transition(context, str(Stage.LOAD_POLICY), reason="state_plan_ready")
        self._emit_runtime_probe(context)
        if context.state in {"", "BOOTSTRAP", str(Stage.LOAD_POLICY)}:
            self._transition(context, state_plan.initial_state, reason="state_plan_initial_state")

        tick = 0
        while tick < state_plan.max_ticks:
            self._check_preempt(context)
            self._advance_scenario(context, plan, tick)
            if self._process_pending_transition(context, plan, tick):
                continue
            current_state = (context.state or "").strip()
            if current_state in state_plan.terminal_states:
                self._transition(context, str(Stage.NOTIFY_AND_ARCHIVE), reason="terminal_state_reached")
                self._transition(context, str(Stage.FINISH), reason="run_completed")
                return
            current_node = state_plan.node_for(current_state, context.blackboard) if current_state else None
            if current_node is None:
                raise RuntimeError(f"unknown_state:{current_state or '<empty>'}")
            # Optimistic execution model: action states execute immediately.
            # State recognition is reserved for transition confirmation and
            # fallback recovery paths, not for pre-action self-verification.
            if current_node.action is not None:
                decision = PolicyDecision(
                    kind="action",
                    action=current_node.action,
                    next_state=current_node.next_state,
                    controller_id=current_node.action.controller_id or current_node.controller_id,
                    context_id=current_node.action.required_context or current_node.context_id,
                    reason="execute_state_action_optimistic",
                )
                self._log_policy_decision(context, tick, current_state, decision)
                self._ensure_decision_context(context, decision)
                self._logs.replay_event(
                    context.run_id,
                    "decision",
                    {
                        "tick": tick,
                        "state": current_state,
                        "kind": decision.kind,
                        "reason": decision.reason,
                        "next_state": decision.next_state,
                        "context_id": decision.context_id or context.active_context_id,
                        "controller_id": decision.controller_id,
                        "action": {
                            "name": decision.action.name,
                            "kind": decision.action.kind,
                        },
                    },
                )
                step = decision.action.to_step()
                stage = self.STEP_STAGE_MAP.get(step.kind)
                if stage:
                    self._transition(context, str(stage), reason=f"intent:{step.name}")
                self._run_step(context, step)
                acting_state = current_state
                reentry_key = f"_action_done:{acting_state}"
                context.retries[reentry_key] = int(context.retries.get(reentry_key, 0)) + 1
                if decision.next_state:
                    self._create_pending_transition(
                        plan=plan,
                        context=context,
                        source_state=acting_state,
                        target_state=decision.next_state,
                        acceptable_targets=self._acceptable_targets_for_pending(
                            source_node=current_node,
                            primary_target=decision.next_state,
                            source_state=acting_state,
                        ),
                        reason=f"action_success:{step.name}",
                        step=step,
                    )
                tick += 1
                continue
            now = perf_counter()
            observe_interval = self._state_scan_interval_seconds(context, current_node.wait_seconds)
            scan_state_key = "_regular_scan_state"
            scan_next_key = "_regular_scan_next_at"
            if context.retries.get(scan_state_key) != current_state:
                context.retries[scan_state_key] = current_state
                context.retries[scan_next_key] = 0.0
            next_scan_at = float(context.retries.get(scan_next_key, 0.0))
            if now < next_scan_at:
                sleep(min(0.2, max(0.01, next_scan_at - now)))
                continue
            expected = self._expected_states_for_scan(context, plan)
            tick_t0 = perf_counter()
            estimate = self._state_estimator.estimate(context, plan, expected_states=expected)
            context.retries[scan_next_key] = perf_counter() + observe_interval
            estimate_ms = round((perf_counter() - tick_t0) * 1000.0, 1)
            # L3 soft-lost: narrow-scan low confidence 3 ticks → force one
            # broad scan. L4 relocalize: if broad scan then still returns a
            # confident non-current state, snap current_state to it even when
            # we'd normally refuse (mid-action, off-expected_next). This is
            # the escape hatch for unannounced drift — e.g. a popup stole
            # focus and none of the planned successors match.
            if expected is not None:
                if estimate.confidence < 0.4:
                    narrow_low = int(context.retries.get("_narrow_scan_low", 0)) + 1
                    context.retries["_narrow_scan_low"] = narrow_low
                    if narrow_low >= 3:
                        context.retries["_narrow_scan_low"] = 0
                        estimate = self._state_estimator.estimate(context, plan, expected_states=None)
                        self._logs.run_event(
                            context.run_id,
                            "narrow_scan_fallback_broad",
                            {"tick": tick, "current_state": context.state},
                        )
                        if self._maybe_relocalize(context, plan, estimate, tick):
                            tick += 1
                            continue
                else:
                    context.retries["_narrow_scan_low"] = 0
            self._logs.run_event(
                context.run_id,
                "state_estimated",
                {
                    "tick": tick,
                    "state": estimate.state,
                    "confidence": estimate.confidence,
                    "signals": estimate.signals,
                    "estimate_ms": estimate_ms,
                    "expected_states": expected,
                    "uncertainty_reason": estimate.uncertainty_reason,
                    "perception_top_confidence": (
                        estimate.perception.top_confidence if estimate.perception is not None else None
                    ),
                    "perception_candidates": (
                        [
                            {
                                "label": c.label,
                                "confidence": c.confidence,
                                "kind": c.kind,
                                "meta": c.meta,
                            }
                            for c in estimate.perception.candidates
                        ]
                        if estimate.perception is not None
                        else []
                    ),
                    "evidence_refs": (estimate.perception.evidence_refs if estimate.perception is not None else []),
                },
            )
            self._logs.replay_event(
                context.run_id,
                "sense",
                {
                    "tick": tick,
                    "state": estimate.state,
                    "confidence": estimate.confidence,
                    "context_id": context.active_context_id,
                    "uncertainty_reason": estimate.uncertainty_reason,
                    "evidence_refs": (estimate.perception.evidence_refs if estimate.perception is not None else []),
                    "candidates": (
                        [
                            {"label": c.label, "confidence": c.confidence, "kind": c.kind}
                            for c in estimate.perception.candidates
                        ]
                        if estimate.perception is not None
                        else []
                    ),
                },
            )

            decision = self._policy_engine.decide(context, plan, estimate)
            self._log_policy_decision(context, tick, estimate.state, decision)
            self._ensure_decision_context(context, decision)
            self._logs.replay_event(
                context.run_id,
                "decision",
                {
                    "tick": tick,
                    "state": estimate.state,
                    "kind": decision.kind,
                    "reason": decision.reason,
                    "next_state": decision.next_state,
                    "context_id": decision.context_id or context.active_context_id,
                    "controller_id": decision.controller_id,
                    "action": (
                        {
                            "name": decision.action.name,
                            "kind": decision.action.kind,
                        }
                        if decision.action is not None
                        else None
                    ),
                },
            )

            if decision.kind == "finish":
                self._transition(context, str(Stage.NOTIFY_AND_ARCHIVE), reason=decision.reason or "policy_finish")
                self._transition(context, str(Stage.FINISH), reason="run_completed")
                return

            if decision.kind == "fail":
                raise RuntimeError(decision.error or f"policy_fail:{decision.reason}")

            if decision.kind == "transition":
                if not decision.next_state:
                    raise RuntimeError("policy_transition_missing_next_state")
                self._transition(context, decision.next_state, reason=decision.reason or "policy_transition")
                tick += 1
                continue

            if decision.kind == "wait":
                sleep(max(0.01, float(decision.wait_seconds)))
                tick += 1
                continue

            if decision.kind == "action":
                if decision.action is None:
                    raise RuntimeError("policy_action_missing_action")
                step = decision.action.to_step()
                stage = self.STEP_STAGE_MAP.get(step.kind)
                if stage:
                    self._transition(context, str(stage), reason=f"intent:{step.name}")
                self._run_step(context, step)
                # Track that the *acting* state's action has executed (for
                # re-entry detection). Must use context.state — the state the
                # policy acted on — not estimate.state, which may be a
                # phantom recognition of some other state.
                acting_state = context.state or estimate.state
                reentry_key = f"_action_done:{acting_state}"
                context.retries[reentry_key] = int(context.retries.get(reentry_key, 0)) + 1
                if decision.next_state:
                    acting_node = (
                        state_plan.node_for(acting_state, context.blackboard)
                        if state_plan is not None
                        else None
                    )
                    self._create_pending_transition(
                        plan=plan,
                        context=context,
                        source_state=acting_state,
                        target_state=decision.next_state,
                        acceptable_targets=self._acceptable_targets_for_pending(
                            source_node=acting_node,
                            primary_target=decision.next_state,
                            source_state=acting_state,
                        ),
                        reason=f"action_success:{step.name}",
                        step=step,
                    )
                tick += 1
                continue

            raise RuntimeError(f"unsupported_policy_decision:{decision.kind}")

        raise RuntimeError(f"state_driven_tick_limit_exceeded:max_ticks={state_plan.max_ticks}")

    def _emit_runtime_probe(self, context: RunContext) -> None:
        backend_name = ""
        backend_size: tuple[int, int] | None = None
        try:
            inner = getattr(self._state_estimator, "_backend", None)
            if inner is not None:
                backend_name = type(inner).__name__
                if hasattr(inner, "size"):
                    try:
                        backend_size = inner.size()
                    except Exception:
                        backend_size = None
        except Exception:
            pass
        save_frames = os.getenv("ACGI_SAVE_FRAMES", "").strip() in {"1", "true", "True"}
        self._logs.run_event(
            context.run_id,
            "runtime_probe",
            {
                "backend": backend_name or "unknown",
                "screen_size": list(backend_size) if backend_size else None,
                "ui_automation_mode": os.getenv("UI_AUTOMATION_BACKEND", "auto"),
                "save_frames": save_frames,
                "frames_dir": os.getenv("ACGI_FRAMES_DIR", "./runtime/frames") if save_frames else None,
            },
        )

    def _maybe_relocalize(
        self,
        context: RunContext,
        plan: WorkflowPlan,
        estimate: Any,
        tick: int,
    ) -> bool:
        """L4: snap context.state to the broad-scan winner when drifted.

        Returns True when we relocalized (caller should skip the rest of
        this tick — next tick will re-plan from the new state). Relocalize
        only fires when:
          - broad scan returned a confident (>=0.75) state label
          - that label is a real plan state, not context.state, and is
            not already a successor we were scanning for (a real successor
            should have been caught by narrow scan).

        L5 escalation: if the state we are leaving is marked ``destructive``,
        we refuse to silently relocalize and raise ``InterruptError``
        instead. The assumption is that a destructive node ran code with
        side effects and silently advancing would hide that state from the
        operator.
        """
        sp = plan.state_plan
        if sp is None:
            return False
        target = (estimate.state or "").strip()
        if not target or target == context.state:
            return False
        if estimate.confidence < 0.75:
            return False
        known = {n.state for n in sp.nodes} | set(sp.terminal_states)
        if target not in known:
            return False

        current_node = sp.node_for(context.state, context.blackboard) if context.state else None
        if current_node is not None and current_node.recoverability == "destructive":
            self._logs.run_event(
                context.run_id,
                "relocalize_escalated",
                {
                    "tick": tick,
                    "from": context.state,
                    "observed": target,
                    "confidence": estimate.confidence,
                    "reason": "destructive_node_no_silent_relocalize",
                },
            )
            raise InterruptError(
                f"relocalize_on_destructive:{context.state}->{target}"
            )

        # Clear pending transition to avoid spurious commit on the new state.
        context.pending_transition = {}
        self._logs.run_event(
            context.run_id,
            "relocalized",
            {
                "tick": tick,
                "from": context.state,
                "to": target,
                "confidence": estimate.confidence,
                "reason": "broad_scan_drift",
            },
        )
        self._transition(context, target, reason="relocalize_broad_scan")
        return True

    def _advance_scenario(self, context: RunContext, plan: WorkflowPlan, tick: int) -> None:
        """Push current_goal to the blackboard based on plan.scenario_spec.

        No-op when the plan has no scenario. Logs goal changes so the replay
        shows *why* a guard flipped.
        """
        spec = plan.scenario_spec
        if spec is None:
            return
        before = context.blackboard.get("current_goal")
        after = advance_scenario(spec, context.blackboard)
        if before != after:
            self._logs.run_event(
                context.run_id,
                "scenario_goal_changed",
                {"tick": tick, "from": before, "to": after, "done": after is None},
            )

    def _expected_states_for_scan(
        self, context: RunContext, plan: WorkflowPlan
    ) -> list[str] | None:
        """Derive narrow-scan candidate list from context.state.

        Returns None for broad scan when:
          - current state is unknown / missing
          - current node is not in the plan
          - current node is a hub (expected_next is None)
        """
        current = (context.state or "").strip()
        if not current:
            return None
        sp = plan.state_plan
        if sp is None:
            return None
        node = sp.node_for(current, context.blackboard)
        if node is None or node.expected_next is None:
            return None

        # Action states should not continuously OCR-scan successor states.
        # We only need "am I still in current state?" before issuing action;
        # successor observation is handled by pending_transition processing.
        # This keeps steady-state tick cost low and avoids launch-stage stalls
        # when expected_next carries heavy OCR recognition.
        if node.action is not None:
            return [current]

        out: list[str] = []
        # Observation-only states should still verify their own recognition
        # before transitioning out; otherwise a non-recognizing successor can
        # cause context-fallback and blind transition.
        if node.action is None and node.recognition:
            out.append(current)
        for s in node.expected_next:
            if s not in out:
                out.append(s)
        return out

    def _create_pending_transition(
        self,
        *,
        plan: WorkflowPlan,
        context: RunContext,
        source_state: str,
        target_state: str,
        acceptable_targets: list[str] | None,
        reason: str,
        step: WorkflowStep,
    ) -> None:
        now = perf_counter()
        settle_seconds = max(0.0, float(step.params.get("transition_settle_seconds", 0.3)))
        timeout_seconds = max(settle_seconds + 0.2, float(step.params.get("transition_timeout_seconds", 15.0)))
        require_observed = bool(step.params.get("transition_require_observed", False))
        required_observed_ticks = max(1, int(step.params.get("transition_observed_ticks", 2)))
        observe_interval_seconds = max(
            1.1,
            float(
                step.params.get(
                    "transition_observe_interval_seconds",
                    step.params.get("text_poll_seconds", 1.2),
                )
            ),
        )
        auto_downgraded_observed = False
        acceptable = [str(s).strip() for s in (acceptable_targets or []) if str(s).strip()]
        if target_state not in acceptable:
            acceptable.insert(0, target_state)
        unique_acceptable: list[str] = []
        for s in acceptable:
            if s not in unique_acceptable:
                unique_acceptable.append(s)
        if require_observed:
            has_recognition = False
            if plan.state_plan is not None:
                for st in unique_acceptable:
                    node = plan.state_plan.node_for(st, context.blackboard)
                    if node and node.recognition:
                        has_recognition = True
                        break
            if not has_recognition:
                require_observed = False
                auto_downgraded_observed = True
        context.pending_transition = {
            "source_state": source_state,
            "target_state": target_state,
            "acceptable_targets": unique_acceptable,
            "reason": reason,
            "created_at": now,
            "not_before": now + settle_seconds,
            "deadline": now + timeout_seconds,
            "settle_seconds": settle_seconds,
            "timeout_seconds": timeout_seconds,
            "require_observed": require_observed,
            "required_observed_ticks": required_observed_ticks,
            "observed_ticks": 0,
            "last_observed_target_state": "",
            "observe_interval_seconds": observe_interval_seconds,
            "next_observe_at": now + settle_seconds,
        }
        self._logs.run_event(
            context.run_id,
            "transition_pending_set",
            {
                "source_state": source_state,
                "target_state": target_state,
                "acceptable_targets": unique_acceptable,
                "reason": reason,
                "settle_seconds": settle_seconds,
                "timeout_seconds": timeout_seconds,
                "require_observed": require_observed,
                "required_observed_ticks": required_observed_ticks,
                "observe_interval_seconds": observe_interval_seconds,
                "auto_downgraded_observed": auto_downgraded_observed,
            },
        )

    def _process_pending_transition(self, context: RunContext, plan: WorkflowPlan, tick: int) -> bool:
        pending = context.pending_transition
        if not pending:
            return False

        target_state = str(pending.get("target_state", "")).strip()
        if not target_state:
            context.pending_transition = {}
            return False
        acceptable_targets = [
            str(s).strip()
            for s in pending.get("acceptable_targets", [target_state])
            if str(s).strip()
        ]
        if target_state not in acceptable_targets:
            acceptable_targets.insert(0, target_state)

        now = perf_counter()
        deadline = float(pending.get("deadline", now + 0.2))
        if now > deadline:
            if self._recover_from_transition_timeout(context, plan, tick, target_state, acceptable_targets):
                return True
            raise RuntimeError(
                "transition_timeout:"
                f"{pending.get('source_state', '')}->{target_state},"
                f"reason={pending.get('reason', '')}"
            )

        require_observed = bool(pending.get("require_observed", False))
        not_before = float(pending.get("not_before", now))
        if now < not_before:
            sleep(0.05)
            return True

        if require_observed:
            observe_interval = max(1.1, float(pending.get("observe_interval_seconds", 1.2)))
            next_observe_at = float(pending.get("next_observe_at", not_before))
            if now < next_observe_at:
                sleep(min(0.2, max(0.01, next_observe_at - now)))
                return True
            if self._state_estimator is not None:
                estimate = self._state_estimator.estimate(context, plan, expected_states=acceptable_targets)
                observed_target = estimate.state if estimate.state in acceptable_targets else ""
                last_observed = str(pending.get("last_observed_target_state", "")).strip()
                if observed_target:
                    if observed_target == last_observed:
                        pending["observed_ticks"] = int(pending.get("observed_ticks", 0)) + 1
                    else:
                        pending["observed_ticks"] = 1
                    pending["last_observed_target_state"] = observed_target
                else:
                    pending["observed_ticks"] = 0
                    pending["last_observed_target_state"] = ""
                pending["next_observe_at"] = now + observe_interval
                self._logs.replay_event(
                    context.run_id,
                    "transition_observe",
                    {
                        "tick": tick,
                        "pending_target_state": target_state,
                        "observed_state": estimate.state,
                        "observed_ticks": int(pending.get("observed_ticks", 0)),
                        "required_observed_ticks": int(pending.get("required_observed_ticks", 1)),
                        "require_observed": require_observed,
                        "observe_interval_seconds": observe_interval,
                        "expected_states": acceptable_targets,
                    },
                )
            observed = int(pending.get("observed_ticks", 0))
            required = max(1, int(pending.get("required_observed_ticks", 1)))
            if observed < required:
                sleep(0.1)
                return True

        commit_target = str(pending.get("last_observed_target_state", "")).strip() if require_observed else ""
        if not commit_target:
            commit_target = target_state
        self._transition(context, commit_target, reason=str(pending.get("reason", "pending_transition_committed")))
        self._logs.run_event(
            context.run_id,
            "transition_pending_committed",
            {
                "source_state": pending.get("source_state", ""),
                "target_state": commit_target,
                "reason": pending.get("reason", ""),
                "observed_ticks": int(pending.get("observed_ticks", 0)),
                "acceptable_targets": acceptable_targets,
            },
        )
        context.pending_transition = {}
        return True

    def _recover_from_transition_timeout(
        self,
        context: RunContext,
        plan: WorkflowPlan,
        tick: int,
        target_state: str,
        acceptable_targets: list[str],
    ) -> bool:
        if self._state_estimator is None:
            return False
        cooldown = self._recovery_broad_scan_cooldown_seconds(context)
        now = perf_counter()
        next_allowed = float(context.retries.get("_recovery_broad_scan_next_at", 0.0))
        if now < next_allowed:
            return False
        context.retries["_recovery_broad_scan_next_at"] = now + cooldown
        estimate = self._state_estimator.estimate(context, plan, expected_states=None)
        if estimate.state in acceptable_targets and estimate.confidence >= 0.6:
            self._logs.run_event(
                context.run_id,
                "transition_timeout_commit_acceptable",
                {
                    "tick": tick,
                    "current_state": context.state,
                    "target_state": target_state,
                    "acceptable_targets": acceptable_targets,
                    "committed_state": estimate.state,
                    "confidence": estimate.confidence,
                },
            )
            self._transition(
                context,
                estimate.state,
                reason=f"pending_timeout_observed_acceptable:{target_state}",
            )
            context.pending_transition = {}
            return True
        self._logs.run_event(
            context.run_id,
            "transition_timeout_broad_scan",
            {
                "tick": tick,
                "current_state": context.state,
                "target_state": target_state,
                "observed_state": estimate.state,
                "confidence": estimate.confidence,
                "cooldown_seconds": cooldown,
            },
        )
        return self._maybe_relocalize(context, plan, estimate, tick)

    def _acceptable_targets_for_pending(
        self,
        *,
        source_node: Any | None,
        primary_target: str,
        source_state: str | None = None,
    ) -> list[str]:
        out: list[str] = []
        if primary_target:
            out.append(primary_target)
        source = (source_state or "").strip()
        if source_node is not None and getattr(source_node, "expected_next", None):
            for s in source_node.expected_next:
                s2 = str(s).strip()
                if not s2:
                    continue
                # Don't treat "stay in source state" as successful transition;
                # otherwise pending may commit to self and loop forever.
                if source and s2 == source:
                    continue
                if s2 not in out:
                    out.append(s2)
        return out

    def _state_scan_interval_seconds(self, context: RunContext, node_wait_seconds: float) -> float:
        default_seconds = max(1.1, float(node_wait_seconds))
        manifest = context.manifest if isinstance(context.manifest, dict) else {}
        effective_policy = manifest.get("effective_policy", {})
        if not isinstance(effective_policy, dict):
            return default_seconds
        raw = effective_policy.get("state_scan_interval_seconds", default_seconds)
        try:
            return max(1.1, float(raw))
        except Exception:
            return default_seconds

    def _recovery_broad_scan_cooldown_seconds(self, context: RunContext) -> float:
        default_seconds = 5.0
        manifest = context.manifest if isinstance(context.manifest, dict) else {}
        effective_policy = manifest.get("effective_policy", {})
        if not isinstance(effective_policy, dict):
            return default_seconds
        raw = effective_policy.get("recovery_broad_scan_cooldown_seconds", default_seconds)
        try:
            return max(1.0, float(raw))
        except Exception:
            return default_seconds

    def _log_policy_decision(self, context: RunContext, tick: int, state: str, decision: PolicyDecision) -> None:
        payload: dict[str, Any] = {
            "tick": tick,
            "state": state,
            "kind": decision.kind,
            "reason": decision.reason,
            "next_state": decision.next_state,
            "controller_id": decision.controller_id,
            "context_id": decision.context_id or context.active_context_id,
            "wait_seconds": decision.wait_seconds,
            "explain": {
                "decision_kind": decision.kind,
                "rule_reason": decision.reason,
                "has_action": decision.action is not None,
            },
        }
        if decision.action is not None:
            payload["action"] = {
                "name": decision.action.name,
                "kind": decision.action.kind,
                "max_retries": decision.action.max_retries,
                "backoff_seconds": decision.action.backoff_seconds,
            }
        if decision.error:
            payload["error"] = decision.error

        level = "INFO" if decision.kind != "fail" else "ERROR"
        self._logs.run_event(context.run_id, "policy_decision", payload, level=level)

    def _ensure_decision_context(self, context: RunContext, decision: PolicyDecision) -> None:
        if self._context_manager is None:
            return
        target = (decision.context_id or "").strip()
        if not target:
            return
        switched = self._context_manager.switch_to(context, target, reason=f"policy:{decision.reason or decision.kind}")
        self._logs.run_event(
            context.run_id,
            "context_switched",
            {
                "source_context": switched.source_context,
                "target_context": switched.target_context,
                "reason": switched.reason,
                "decision_kind": decision.kind,
            },
        )

    def _transition(self, context: RunContext, target: str, reason: str) -> None:
        source = context.state
        context.state = target
        context.layered_state.global_layer.state = target
        context.layered_state.global_layer.last_reason = reason
        # Clear per-state counters that are only valid within a single state visit
        for key in [k for k in context.retries.keys() if k.startswith(("_state_seen:", "_observed_seen:"))]:
            context.retries.pop(key, None)
        self._checkpoints.save(context)
        self._logs.state_transition(context.run_id, source, context.state, reason=reason)
        self._logs.replay_event(
            context.run_id,
            "transition",
            {
                "from": source,
                "to": target,
                "reason": reason,
                "context_id": context.active_context_id,
            },
        )

    def _run_step(self, context: RunContext, step: WorkflowStep) -> None:
        max_retries = int(step.params.get("max_retries", 0))
        backoff_seconds = float(step.params.get("backoff_seconds", 0.2))
        required_resources = list(step.params.get("required_resources", []))
        attempt = 0
        while True:
            attempt += 1
            self._check_preempt(context)
            lease = None
            if self._resource_arbiter is not None:
                lease = self._resource_arbiter.acquire(
                    context.run_id,
                    required_resources,
                    timeout_seconds=float(step.params.get("resource_timeout_seconds", 1.0)),
                )
                if lease is None:
                    diag = classify_failure(f"resource_acquire_timeout:{required_resources}")
                    context.last_error = {
                        "action": step.name,
                        "kind": step.kind,
                        "detail": f"resource_acquire_timeout:{required_resources}",
                        "error_code": diag.code,
                        "error_category": diag.category,
                        "hint": diag.hint,
                    }
                    raise RuntimeError(f"resource_acquire_timeout:{required_resources}")
            self._logs.action_event(
                context.run_id,
                action_name=step.name,
                status="started",
                payload={
                    "kind": step.kind,
                    "params": step.params,
                    "attempt": attempt,
                    "context_id": context.active_context_id,
                    "resources": required_resources,
                    "controller_id": context.layered_state.controller_layer.active_controller_id,
                },
            )
            try:
                t0 = perf_counter()
                result = self._runtime.execute(step, context)
                elapsed_ms = int((perf_counter() - t0) * 1000)
            finally:
                if lease is not None:
                    self._resource_arbiter.release(lease)
            if bool(result.get("risk_stopped", False)):
                context.last_error = {
                    "action": step.name,
                    "kind": step.kind,
                    "detail": str(result.get("detail", "risk_stop:risk_detected")),
                    "error_code": "RISK_STOP",
                    "error_category": "safety",
                    "hint": "触发风控停止",
                }
                raise InterruptError(str(result.get("detail", "risk_stop:risk_detected")))
            if bool(result.get("interrupted", False)):
                context.last_error = {
                    "action": step.name,
                    "kind": step.kind,
                    "detail": str(result.get("detail", "interrupted:manual_interrupt")),
                    "error_code": "INTERRUPTED",
                    "error_category": "control",
                    "hint": "收到中断信号",
                }
                raise InterruptError(str(result.get("detail", "interrupted:manual_interrupt")))
            ok = bool(result.get("ok", False))
            if ok:
                context.layered_state.controller_layer.last_status = "succeeded"
                self._logs.action_event(
                    context.run_id,
                    action_name=step.name,
                    status="succeeded",
                    payload={"kind": step.kind, "result": result, "elapsed_ms": elapsed_ms, "attempt": attempt},
                )
                self._logs.replay_event(
                    context.run_id,
                    "action_result",
                    {
                        "action": step.name,
                        "kind": step.kind,
                        "status": "succeeded",
                        "attempt": attempt,
                        "context_id": context.active_context_id,
                        "detail": str(result.get("detail", "")),
                        "evidence_refs": list(result.get("evidence_refs", [])),
                    },
                )
                return

            retryable = bool(result.get("retryable", True))
            context.layered_state.controller_layer.last_status = "failed"
            self._logs.action_event(
                context.run_id,
                action_name=step.name,
                status="failed",
                payload={
                    "kind": step.kind,
                    "result": result,
                    "elapsed_ms": elapsed_ms,
                    "attempt": attempt,
                    "max_retries": max_retries,
                    "retryable": retryable,
                    "error_code": classify_failure(str(result.get("detail", ""))).code,
                    "error_category": classify_failure(str(result.get("detail", ""))).category,
                    "hint": classify_failure(str(result.get("detail", ""))).hint,
                    "state": context.state,
                    "context_id": context.active_context_id,
                    "controller_id": context.layered_state.controller_layer.active_controller_id,
                },
                level="ERROR",
            )
            diag = classify_failure(str(result.get("detail", "")))
            context.last_error = {
                "action": step.name,
                "kind": step.kind,
                "detail": str(result.get("detail", "")),
                "attempt": attempt,
                "max_retries": max_retries,
                "retryable": retryable,
                "error_code": diag.code,
                "error_category": diag.category,
                "hint": diag.hint,
                "state": context.state,
                "context_id": context.active_context_id,
                "controller_id": context.layered_state.controller_layer.active_controller_id,
            }
            self._logs.replay_event(
                context.run_id,
                "action_result",
                {
                    "action": step.name,
                    "kind": step.kind,
                    "status": "failed",
                    "attempt": attempt,
                    "context_id": context.active_context_id,
                    "detail": str(result.get("detail", "")),
                    "retryable": retryable,
                    "evidence_refs": list(result.get("evidence_refs", [])),
                },
            )
            directive = self._build_recovery_directive(
                context=context,
                step=step,
                result=result,
                attempt=attempt,
                max_retries=max_retries,
                retryable=retryable,
                backoff_seconds=backoff_seconds,
            )
            self._logs.run_event(
                context.run_id,
                "recovery_decision",
                {
                    "action": step.name,
                    "attempt": attempt,
                    "decision": directive.decision,
                    "reason": directive.reason,
                    "target_context_id": directive.target_context_id,
                    "extra_retry_budget": directive.extra_retry_budget,
                },
            )
            if directive.decision == "switch_context_then_retry" and self._context_manager and directive.target_context_id:
                self._context_manager.switch_to(context, directive.target_context_id, reason=f"recover:{step.name}")
            if directive.decision == "escalate":
                self._handle_ai_recovery_escalation(context=context, step=step, result=result)
            if directive.decision in {"fail", "escalate"}:
                raise RuntimeError(f"step failed: {step.name}, detail={result}, attempt={attempt}")
            allowed_retry_limit = max_retries + max(0, int(directive.extra_retry_budget))
            if not retryable and directive.decision != "retry":
                raise RuntimeError(f"step failed: {step.name}, detail={result}, attempt={attempt}")
            if attempt > allowed_retry_limit:
                raise RuntimeError(f"step failed: {step.name}, detail={result}, attempt={attempt}")

            self._logs.action_event(
                context.run_id,
                action_name=step.name,
                status="retrying",
                payload={
                    "attempt": attempt,
                    "next_attempt": attempt + 1,
                    "sleep_seconds": directive.backoff_seconds or backoff_seconds,
                    "decision": directive.decision,
                },
                level="WARN",
            )
            sleep(max(0.01, float(directive.backoff_seconds or backoff_seconds)))

    def _build_recovery_directive(
        self,
        *,
        context: RunContext,
        step: WorkflowStep,
        result: dict[str, Any],
        attempt: int,
        max_retries: int,
        retryable: bool,
        backoff_seconds: float,
    ) -> RecoveryDirective:
        if self._recovery_strategy is not None:
            return self._recovery_strategy.plan(
                step=step,
                context=context,
                result=result,
                attempt=attempt,
                max_retries=max_retries,
            )
        if retryable and attempt <= max_retries:
            return RecoveryDirective(decision="retry", reason="default_retry", backoff_seconds=backoff_seconds)
        return RecoveryDirective(decision="fail", reason="default_fail", backoff_seconds=backoff_seconds)

    def _handle_ai_recovery_escalation(self, *, context: RunContext, step: WorkflowStep, result: dict[str, Any]) -> None:
        if self._ai_recovery_planner is None:
            self._logs.run_event(
                context.run_id,
                "ai_recovery_skipped",
                {"action": step.name, "reason": "planner_not_configured"},
                level="WARN",
            )
            return
        proposal = self._ai_recovery_planner.propose(step=step, context=context, failure=result)
        self._logs.run_event(
            context.run_id,
            "ai_recovery_proposal",
            {
                "action": step.name,
                "proposal": proposal,
            },
            level="WARN",
        )

    def _check_preempt(self, context: RunContext) -> None:
        if self._risk_check is not None:
            hit, reason = self._risk_check(context.run_id)
            if hit:
                context.last_error = {
                    "detail": f"risk_stop:{reason or 'risk_detected'}",
                    "error_code": "RISK_STOP",
                    "error_category": "safety",
                    "hint": "触发风控停止",
                    "state": context.state,
                    "context_id": context.active_context_id,
                }
                raise InterruptError(f"risk_stop:{reason or 'risk_detected'}")
        if self._interrupt_check is not None:
            hit, reason = self._interrupt_check(context.run_id)
            if hit:
                context.last_error = {
                    "detail": f"interrupted:{reason or 'manual_interrupt'}",
                    "error_code": "INTERRUPTED",
                    "error_category": "control",
                    "hint": "收到中断信号",
                    "state": context.state,
                    "context_id": context.active_context_id,
                }
                raise InterruptError(f"interrupted:{reason or 'manual_interrupt'}")
