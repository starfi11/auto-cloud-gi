from __future__ import annotations

from typing import Protocol

from src.domain.workflow import WorkflowStep
from src.kernel.context_store import RunContext


class ControllerPort(Protocol):
    @property
    def controller_id(self) -> str:
        ...

    def supports(self, step: WorkflowStep) -> bool:
        ...

    def execute(self, step: WorkflowStep, context: RunContext) -> dict[str, object]:
        ...
