from __future__ import annotations

from time import perf_counter, sleep
from typing import Callable, Any, Protocol

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
        if context.state in {"", "BOOTSTRAP", str(Stage.LOAD_POLICY)}:
            self._transition(context, state_plan.initial_state, reason="state_plan_initial_state")

        for tick in range(state_plan.max_ticks):
            self._check_preempt(context)
            if self._process_pending_transition(context, plan, tick):
                continue
            expected = self._expected_states_for_scan(context, plan)
            estimate = self._state_estimator.estimate(context, plan, expected_states=expected)
            # Narrow-scan low-confidence fallback: if we've been getting weak
            # signals under narrow scan for several ticks, try one broad scan
            # to catch unexpected drift (e.g. expected_next misconfigured or
            # game went to an unforeseen state).
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
                    "uncertainty_reason": estimate.uncertainty_reason,
                    "perception_top_confidence": (
                        estimate.perception.top_confidence if estimate.perception is not None else None
                    ),
                    "perception_candidates": (
                        [
                            {"label": c.label, "confidence": c.confidence, "kind": c.kind}
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
                continue

            if decision.kind == "wait":
                sleep(max(0.01, float(decision.wait_seconds)))
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
                    self._create_pending_transition(
                        plan=plan,
                        context=context,
                        source_state=acting_state,
                        target_state=decision.next_state,
                        reason=f"action_success:{step.name}",
                        step=step,
                    )
                continue

            raise RuntimeError(f"unsupported_policy_decision:{decision.kind}")

        raise RuntimeError(f"state_driven_tick_limit_exceeded:max_ticks={state_plan.max_ticks}")

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
        node = sp.node_for(current)
        if node is None or node.expected_next is None:
            return None
        out = [current]
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
        reason: str,
        step: WorkflowStep,
    ) -> None:
        now = perf_counter()
        settle_seconds = max(0.0, float(step.params.get("transition_settle_seconds", 0.3)))
        timeout_seconds = max(settle_seconds + 0.2, float(step.params.get("transition_timeout_seconds", 15.0)))
        require_observed = bool(step.params.get("transition_require_observed", False))
        required_observed_ticks = max(1, int(step.params.get("transition_observed_ticks", 2)))
        auto_downgraded_observed = False
        if require_observed:
            target_node = plan.state_plan.node_for(target_state) if plan.state_plan is not None else None
            has_recognition = bool(target_node and target_node.recognition)
            if not has_recognition:
                require_observed = False
                auto_downgraded_observed = True
        context.pending_transition = {
            "source_state": source_state,
            "target_state": target_state,
            "reason": reason,
            "created_at": now,
            "not_before": now + settle_seconds,
            "deadline": now + timeout_seconds,
            "settle_seconds": settle_seconds,
            "timeout_seconds": timeout_seconds,
            "require_observed": require_observed,
            "required_observed_ticks": required_observed_ticks,
            "observed_ticks": 0,
        }
        self._logs.run_event(
            context.run_id,
            "transition_pending_set",
            {
                "source_state": source_state,
                "target_state": target_state,
                "reason": reason,
                "settle_seconds": settle_seconds,
                "timeout_seconds": timeout_seconds,
                "require_observed": require_observed,
                "required_observed_ticks": required_observed_ticks,
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

        now = perf_counter()
        deadline = float(pending.get("deadline", now + 0.2))
        if now > deadline:
            raise RuntimeError(
                "transition_timeout:"
                f"{pending.get('source_state', '')}->{target_state},"
                f"reason={pending.get('reason', '')}"
            )

        require_observed = bool(pending.get("require_observed", False))
        if self._state_estimator is not None:
            # During a pending transition we only care whether we've arrived
            # at target_state (or are still sitting in source_state). Narrow
            # scan to those two states to keep OCR cost low.
            pending_expected: list[str] | None = [target_state]
            src = str(pending.get("source_state", "")).strip()
            if src and src not in pending_expected:
                pending_expected.append(src)
            estimate = self._state_estimator.estimate(
                context, plan, expected_states=pending_expected
            )
            if estimate.state == target_state:
                pending["observed_ticks"] = int(pending.get("observed_ticks", 0)) + 1
            else:
                pending["observed_ticks"] = 0

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
                },
            )

        not_before = float(pending.get("not_before", now))
        if now < not_before:
            sleep(0.05)
            return True

        if require_observed:
            observed = int(pending.get("observed_ticks", 0))
            required = max(1, int(pending.get("required_observed_ticks", 1)))
            if observed < required:
                sleep(0.05)
                return True

        self._transition(context, target_state, reason=str(pending.get("reason", "pending_transition_committed")))
        self._logs.run_event(
            context.run_id,
            "transition_pending_committed",
            {
                "source_state": pending.get("source_state", ""),
                "target_state": target_state,
                "reason": pending.get("reason", ""),
                "observed_ticks": int(pending.get("observed_ticks", 0)),
            },
        )
        context.pending_transition = {}
        return True

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
