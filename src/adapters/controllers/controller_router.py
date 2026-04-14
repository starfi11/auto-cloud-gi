from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.domain.workflow import WorkflowStep
from src.infra.log_manager import LogManager
from src.kernel.context_manager import ContextManager
from src.kernel.context_store import RunContext
from src.ports.controller_port import ControllerPort


@dataclass
class ControllerRouter:
    controllers: Sequence[ControllerPort]
    context_manager: ContextManager
    logs: LogManager

    def execute(self, step: WorkflowStep, context: RunContext) -> dict[str, object]:
        required_context = str(step.params.get("required_context", "")).strip()
        if required_context:
            switched = self.context_manager.switch_to(context, required_context, reason=f"step:{step.name}")
            self.logs.run_event(
                context.run_id,
                "context_switched",
                {
                    "action": step.name,
                    "source_context": switched.source_context,
                    "target_context": switched.target_context,
                    "reason": switched.reason,
                },
            )

        preferred_controller = str(step.params.get("controller_id", "")).strip()
        if preferred_controller:
            for controller in self.controllers:
                if controller.controller_id == preferred_controller:
                    context.layered_state.controller_layer.active_controller_id = controller.controller_id
                    context.layered_state.controller_layer.last_action = step.name
                    self.logs.run_event(
                        context.run_id,
                        "controller_selected",
                        {
                            "action": step.name,
                            "kind": step.kind,
                            "controller_id": controller.controller_id,
                            "context_id": context.active_context_id,
                            "selection": "preferred",
                        },
                    )
                    return controller.execute(step, context)

        for controller in self.controllers:
            if controller.supports(step):
                context.layered_state.controller_layer.active_controller_id = controller.controller_id
                context.layered_state.controller_layer.last_action = step.name
                self.logs.run_event(
                    context.run_id,
                    "controller_selected",
                    {
                        "action": step.name,
                        "kind": step.kind,
                        "controller_id": controller.controller_id,
                        "context_id": context.active_context_id,
                        "selection": "auto",
                    },
                )
                return controller.execute(step, context)

        context.layered_state.controller_layer.last_action = step.name
        context.layered_state.controller_layer.last_status = "failed"
        return {
            "ok": False,
            "retryable": False,
            "detail": f"no_controller_for_step:{step.kind}",
        }
