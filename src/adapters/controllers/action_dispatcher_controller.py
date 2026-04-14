from __future__ import annotations

from dataclasses import dataclass

from src.app.action_dispatcher import ActionDispatcher
from src.domain.workflow import WorkflowStep
from src.kernel.context_store import RunContext


@dataclass
class ActionDispatcherController:
    _controller_id: str
    dispatcher: ActionDispatcher
    supported_prefixes: tuple[str, ...]

    @property
    def controller_id(self) -> str:
        return self._controller_id

    def supports(self, step: WorkflowStep) -> bool:
        return any(step.kind.startswith(prefix) for prefix in self.supported_prefixes)

    def execute(self, step: WorkflowStep, context: RunContext) -> dict[str, object]:
        if not self.supports(step):
            return {
                "ok": False,
                "retryable": False,
                "detail": f"unsupported_step_for_controller:{self._controller_id}:{step.kind}",
            }
        return self.dispatcher.execute(step, context)
