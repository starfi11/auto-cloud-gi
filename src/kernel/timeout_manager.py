from __future__ import annotations

from dataclasses import dataclass
from time import monotonic


@dataclass(frozen=True)
class Timeout:
    seconds: float
    started_at: float

    @staticmethod
    def start(seconds: float) -> "Timeout":
        return Timeout(seconds=seconds, started_at=monotonic())

    def is_expired(self) -> bool:
        return (monotonic() - self.started_at) >= self.seconds
