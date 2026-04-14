from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Any

from src.domain.workflow import WorkflowStep
from src.kernel.context_store import RunContext
from src.ports.assistant_runtime_port import AssistantRuntimePort
from src.ports.game_runtime_port import GameRuntimePort

SignalProbe = Callable[[], tuple[bool, str]]


class Action(ABC):
    def __init__(self, step: WorkflowStep) -> None:
        self.step = step

    @property
    def name(self) -> str:
        return self.step.name

    @property
    def kind(self) -> str:
        return self.step.kind

    @property
    def params(self) -> dict[str, Any]:
        return self.step.params

    @abstractmethod
    def execute(self, context: RunContext) -> dict[str, Any]:
        raise NotImplementedError

    def _with_context_meta(self, context: RunContext) -> dict[str, Any]:
        merged = dict(self.params)
        merged.setdefault("run_id", context.run_id)
        merged.setdefault("state", context.state)
        merged.setdefault("context_id", context.active_context_id)
        return merged


@dataclass
class StartCloudGameAction(Action):
    step: WorkflowStep
    game_runtime: GameRuntimePort

    def execute(self, context: RunContext) -> dict[str, Any]:
        return self.game_runtime.launch(self._with_context_meta(context))


@dataclass
class EnterQueueAction(Action):
    step: WorkflowStep
    game_runtime: GameRuntimePort

    def execute(self, context: RunContext) -> dict[str, Any]:
        return self.game_runtime.enter_queue(self._with_context_meta(context))


@dataclass
class WaitGameReadyAction(Action):
    step: WorkflowStep
    game_runtime: GameRuntimePort
    interrupt_probe: SignalProbe | None = None
    risk_probe: SignalProbe | None = None

    def execute(self, context: RunContext) -> dict[str, Any]:
        return self.game_runtime.wait_scene_ready(
            self._with_context_meta(context),
            interrupt_check=self.interrupt_probe,
            risk_check=self.risk_probe,
        )


@dataclass
class LaunchAssistantAction(Action):
    step: WorkflowStep
    assistant_runtime: AssistantRuntimePort

    def execute(self, context: RunContext) -> dict[str, Any]:
        return self.assistant_runtime.launch(self._with_context_meta(context))


@dataclass
class DriveAssistantAction(Action):
    step: WorkflowStep
    assistant_runtime: AssistantRuntimePort

    def execute(self, context: RunContext) -> dict[str, Any]:
        options = self._with_context_meta(context)
        scenario = str(options.get("scenario", "default"))
        return self.assistant_runtime.drive(scenario=scenario, options=options)


@dataclass
class CollectArtifactsAction(Action):
    step: WorkflowStep
    assistant_runtime: AssistantRuntimePort

    def execute(self, context: RunContext) -> dict[str, Any]:
        return self.assistant_runtime.collect(self._with_context_meta(context))
