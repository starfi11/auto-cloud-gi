from __future__ import annotations

from typing import Protocol, Any

from src.domain.recovery import RecoveryDirective
from src.domain.workflow import WorkflowStep
from src.kernel.context_store import RunContext


class RecoveryStrategyPort(Protocol):
    def plan(
        self,
        *,
        step: WorkflowStep,
        context: RunContext,
        result: dict[str, Any],
        attempt: int,
        max_retries: int,
    ) -> RecoveryDirective:
        ...
