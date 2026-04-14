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

        observed_state = estimate.state
        current_state = context.state or state_plan.initial_state

        # Recognizer-driven transition: recognizer reports a different state with enough confidence.
        if observed_state != current_state and observed_state:
            observed_node = state_plan.node_for(observed_state)
            if observed_state in state_plan.terminal_states and estimate.confidence >= 0.65:
                return PolicyDecision(kind="finish", reason="terminal_state_observed")
            if observed_node is not None and estimate.confidence >= 0.6:
                seen_key = f"_observed_seen:{observed_state}"
                seen = int(context.retries.get(seen_key, 0)) + 1
                context.retries[seen_key] = seen
                required_seen = max(1, int(observed_node.stable_ticks))
                if seen < required_seen:
                    return PolicyDecision(
                        kind="wait",
                        reason=f"observed_state_settling:{seen}/{required_seen}",
                        wait_seconds=max(0.05, observed_node.wait_seconds),
                        controller_id=observed_node.controller_id,
                        context_id=observed_node.context_id,
                    )
                return PolicyDecision(
                    kind="transition",
                    next_state=observed_state,
                    controller_id=observed_node.controller_id,
                    context_id=observed_node.context_id,
                    reason="observed_state_sync",
                )

        if current_state in state_plan.terminal_states:
            return PolicyDecision(kind="finish", reason="terminal_state_reached")

        node = state_plan.node_for(current_state)
        if node is None:
            return PolicyDecision(
                kind="fail",
                error=f"unknown_state:{current_state}",
                reason="state_not_in_plan",
            )

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

        if estimate.confidence < 0.4:
            return PolicyDecision(
                kind="wait",
                reason=f"low_confidence:{round(estimate.confidence, 3)}",
                wait_seconds=max(0.1, node.wait_seconds),
                controller_id=node.controller_id,
                context_id=node.context_id,
            )

        if node.action is not None:
            return PolicyDecision(
                kind="action",
                action=node.action,
                next_state=node.next_state,
                controller_id=node.action.controller_id or node.controller_id,
                context_id=node.action.required_context or node.context_id,
                reason="execute_state_action",
            )

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
