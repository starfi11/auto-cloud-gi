from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


RecoveryDecision = Literal["retry", "switch_context_then_retry", "fail", "escalate"]


@dataclass(frozen=True)
class RecoveryDirective:
    decision: RecoveryDecision
    reason: str
    target_context_id: str = ""
    backoff_seconds: float = 0.2
    extra_retry_budget: int = 0
