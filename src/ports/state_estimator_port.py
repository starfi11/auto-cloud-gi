from __future__ import annotations

from typing import Protocol

from src.domain.state_kernel import StateEstimate
from src.domain.workflow import WorkflowPlan
from src.kernel.context_store import RunContext


class StateEstimatorPort(Protocol):
    def estimate(self, context: RunContext, plan: WorkflowPlan) -> StateEstimate:
        ...
