from __future__ import annotations

from src.domain.state_kernel import StateEstimate
from src.domain.workflow import WorkflowPlan
from src.kernel.context_store import RunContext
from src.ports.state_estimator_port import StateEstimatorPort


class ContextStateEstimator(StateEstimatorPort):
    def estimate(
        self,
        context: RunContext,
        plan: WorkflowPlan,
        expected_states: list[str] | None = None,
    ) -> StateEstimate:
        state = context.state
        if not state and plan.state_plan is not None:
            state = plan.state_plan.initial_state
        return StateEstimate(
            state=state or "BOOTSTRAP",
            confidence=1.0,
            signals={"source": "context", "context_id": context.active_context_id},
            uncertainty_reason="",
        )
