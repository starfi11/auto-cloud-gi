from __future__ import annotations

from typing import Protocol, Any

from src.domain.workflow import WorkflowStep
from src.kernel.context_store import RunContext


class AiRecoveryPlannerPort(Protocol):
    def propose(
        self,
        *,
        step: WorkflowStep,
        context: RunContext,
        failure: dict[str, Any],
    ) -> dict[str, Any]:
        ...
