from __future__ import annotations

from typing import Protocol

from src.domain.run_request import RunRequest
from src.domain.workflow import WorkflowPlan


class AutomationProfilePort(Protocol):
    @property
    def profile_name(self) -> str:
        ...

    def build_plan(self, request: RunRequest) -> WorkflowPlan:
        ...
