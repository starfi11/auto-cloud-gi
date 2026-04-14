from __future__ import annotations

from typing import Protocol

from src.domain.state_kernel import PolicyDecision, StateEstimate
from src.domain.workflow import WorkflowPlan
from src.kernel.context_store import RunContext


class PolicyEnginePort(Protocol):
    def decide(self, context: RunContext, plan: WorkflowPlan, estimate: StateEstimate) -> PolicyDecision:
        ...
