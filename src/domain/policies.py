from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EffectivePolicy:
    profile: dict[str, Any] = field(default_factory=dict)
    overrides: dict[str, Any] = field(default_factory=dict)

    def materialize(self) -> dict[str, Any]:
        merged = dict(self.profile)
        merged.update(self.overrides)
        return merged
