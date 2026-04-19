from __future__ import annotations

from src.domain.state_kernel import PolicyDecision, StateEstimate
from src.domain.workflow import WorkflowPlan
from src.kernel.context_store import RunContext
from src.ports.policy_engine_port import PolicyEnginePort


class TablePolicyEngine(PolicyEnginePort):
    def decide(self, context: RunContext, plan: WorkflowPlan, estimate: StateEstimate) -> PolicyDecision:
        state_plan = plan.state_plan
        if state_plan is None:
            return PolicyDecision(kind="fail", error="missing_state_plan", reason="state_plan_required")

        current_state = context.state or state_plan.initial_state
        if current_state in state_plan.terminal_states:
            return PolicyDecision(kind="finish", reason="terminal_state_reached")

        current_node = state_plan.node_for(current_state, context.blackboard)
        if current_node is None:
            return PolicyDecision(
                kind="fail",
                error=f"unknown_state:{current_state}",
                reason="state_not_in_plan",
            )

        node = current_node

        stable_key = f"_state_seen:{current_state}"
        seen = int(context.retries.get(stable_key, 0)) + 1
        context.retries[stable_key] = seen
        required_seen = max(1, int(node.stable_ticks))
        if seen < required_seen:
            return PolicyDecision(
                kind="wait",
                reason=f"state_settling:{seen}/{required_seen}",
                wait_seconds=max(0.1, node.wait_seconds),
                controller_id=node.controller_id,
                context_id=node.context_id,
            )

        if node.action is not None:
            context.retries.pop(f"_state_low_conf:{current_state}", None)
            return PolicyDecision(
                kind="action",
                action=node.action,
                next_state=node.next_state,
                controller_id=node.action.controller_id or node.controller_id,
                context_id=node.action.required_context or node.context_id,
                reason="execute_state_action",
            )

        if estimate.confidence < 0.4:
            low_conf_key = f"_state_low_conf:{current_state}"
            low_conf_ticks = int(context.retries.get(low_conf_key, 0)) + 1
            context.retries[low_conf_key] = low_conf_ticks
            waited_seconds = low_conf_ticks * max(0.1, node.wait_seconds)
            stuck_timeout_seconds = self._state_stuck_timeout_seconds(context)
            if waited_seconds >= stuck_timeout_seconds:
                return PolicyDecision(
                    kind="fail",
                    error=f"state_stuck_no_signal:{current_state}:waited={round(waited_seconds, 1)}s",
                    reason="state_stuck_no_signal",
                    controller_id=node.controller_id,
                    context_id=node.context_id,
                )
            return PolicyDecision(
                kind="wait",
                reason=f"low_confidence:{round(estimate.confidence, 3)}",
                wait_seconds=max(0.1, node.wait_seconds),
                controller_id=node.controller_id,
                context_id=node.context_id,
            )
        context.retries.pop(f"_state_low_conf:{current_state}", None)

        if node.next_state:
            return PolicyDecision(
                kind="transition",
                next_state=node.next_state,
                controller_id=node.controller_id,
                context_id=node.context_id,
                reason="state_transition_without_action",
            )

        return PolicyDecision(
            kind="wait",
            wait_seconds=node.wait_seconds,
            controller_id=node.controller_id,
            context_id=node.context_id,
            reason="state_wait",
        )

    def _state_stuck_timeout_seconds(self, context: RunContext) -> float:
        default_seconds = 25.0
        manifest = context.manifest if isinstance(context.manifest, dict) else {}
        effective_policy = manifest.get("effective_policy", {})
        if not isinstance(effective_policy, dict):
            return default_seconds
        raw = effective_policy.get("state_stuck_timeout_seconds", default_seconds)
        try:
            return max(5.0, float(raw))
        except Exception:
            return default_seconds
