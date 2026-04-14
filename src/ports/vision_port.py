from __future__ import annotations

from typing import Protocol, Any
from src.domain.perception import PerceptionResult


class VisionPort(Protocol):
    def detect(self, scene_spec: dict[str, Any]) -> PerceptionResult:
        ...
