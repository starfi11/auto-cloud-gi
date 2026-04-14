from __future__ import annotations

from typing import Protocol


class RetryPort(Protocol):
    def schedule_retry(self, run_id: str, reason: str) -> bool:
        ...
