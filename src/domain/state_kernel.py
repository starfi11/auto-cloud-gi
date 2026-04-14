from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.domain.perception import PerceptionResult
from src.domain.workflow import ActionIntent


DecisionType = Literal["action", "wait", "transition", "finish", "fail"]


@dataclass(frozen=True)
class StateEstimate:
    state: str
    confidence: float = 1.0
    signals: dict[str, Any] = field(default_factory=dict)
    perception: PerceptionResult | None = None
    uncertainty_reason: str = ""


@dataclass(frozen=True)
class PolicyDecision:
    kind: DecisionType
    reason: str = ""
    action: ActionIntent | None = None
    next_state: str | None = None
    controller_id: str | None = None
    context_id: str | None = None
    wait_seconds: float = 0.2
    error: str = ""
