from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PerceptionCandidate:
    label: str
    confidence: float
    kind: str = "unknown"
    bbox: tuple[int, int, int, int] | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PerceptionResult:
    ok: bool
    scene_id: str
    candidates: list[PerceptionCandidate] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    uncertainty_reason: str = ""

    @property
    def top_confidence(self) -> float:
        if not self.candidates:
            return 0.0
        return max(c.confidence for c in self.candidates)
