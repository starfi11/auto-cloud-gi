from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.domain.actions import (
    Action,
    CollectArtifactsAction,
    DriveAssistantAction,
    EnterQueueAction,
    LaunchAssistantAction,
    StartCloudGameAction,
    WaitGameReadyAction,
)
from src.domain.workflow import WorkflowStep
from src.kernel.context_store import RunContext
from src.ports.assistant_runtime_port import AssistantRuntimePort
from src.ports.game_runtime_port import GameRuntimePort

SignalGetter = Callable[[str], tuple[bool, str]]


@dataclass
class ActionDispatcher:
    game_runtime: GameRuntimePort
    assistant_runtime: AssistantRuntimePort
    interrupt_check: SignalGetter | None = None
    risk_check: SignalGetter | None = None

    def create_action(self, step: WorkflowStep, context: RunContext) -> Action:
        if step.kind == "game.launch":
            return StartCloudGameAction(step=step, game_runtime=self.game_runtime)
        if step.kind == "game.queue.enter":
            return EnterQueueAction(step=step, game_runtime=self.game_runtime)
        if step.kind == "game.wait.scene":
            return WaitGameReadyAction(
                step=step,
                game_runtime=self.game_runtime,
                interrupt_probe=(lambda: self.interrupt_check(context.run_id)) if self.interrupt_check else None,
                risk_probe=(lambda: self.risk_check(context.run_id)) if self.risk_check else None,
            )
        if step.kind == "assistant.launch":
            return LaunchAssistantAction(step=step, assistant_runtime=self.assistant_runtime)
        if step.kind == "assistant.drive":
            return DriveAssistantAction(step=step, assistant_runtime=self.assistant_runtime)
        if step.kind == "system.collect":
            return CollectArtifactsAction(step=step, assistant_runtime=self.assistant_runtime)

        raise ValueError(f"unsupported step kind: {step.kind}")

    def execute(self, step: WorkflowStep, context: RunContext) -> dict[str, object]:
        action = self.create_action(step, context)
        return action.execute(context)
