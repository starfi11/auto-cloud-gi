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

        state = estimate.state
        if state in state_plan.terminal_states:
            return PolicyDecision(kind="finish", reason="terminal_state_reached")

        node = state_plan.node_for(state)
        if node is None:
            return PolicyDecision(
                kind="fail",
                error=f"unknown_state:{state}",
                reason="state_not_in_plan",
            )

        if estimate.confidence < 0.45:
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
