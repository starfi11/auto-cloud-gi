from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.domain.recovery import RecoveryDirective
from src.domain.workflow import WorkflowStep
from src.kernel.context_store import RunContext
from src.ports.recovery_strategy_port import RecoveryStrategyPort


@dataclass
class TableRecoveryStrategy(RecoveryStrategyPort):
    def plan(
        self,
        *,
        step: WorkflowStep,
        context: RunContext,
        result: dict[str, Any],
        attempt: int,
        max_retries: int,
    ) -> RecoveryDirective:
        detail = str(result.get("detail", ""))
        if "focus_lost" in detail or "window_not_foreground" in detail:
            target = str(step.params.get("required_context", context.active_context_id))
            return RecoveryDirective(
                decision="switch_context_then_retry",
                reason="recover_focus",
                target_context_id=target,
                backoff_seconds=0.2,
                extra_retry_budget=1,
            )
        if bool(result.get("retryable", True)) and attempt <= max_retries:
            return RecoveryDirective(decision="retry", reason="runtime_retryable", backoff_seconds=0.2)
        return RecoveryDirective(decision="fail", reason="non_retryable_or_budget_exhausted")
