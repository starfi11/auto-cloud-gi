from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.domain.workflow import WorkflowStep
from src.kernel.context_store import RunContext
from src.ports.ai_recovery_planner_port import AiRecoveryPlannerPort


@dataclass
class NoopAiRecoveryPlanner(AiRecoveryPlannerPort):
    def propose(
        self,
        *,
        step: WorkflowStep,
        context: RunContext,
        failure: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "mode": "noop",
            "step": step.name,
            "suggestion": "manual_review",
            "context_id": context.active_context_id,
            "detail": str(failure.get("detail", "")),
        }
