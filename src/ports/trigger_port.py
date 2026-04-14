from __future__ import annotations

from typing import Protocol

from src.domain.run_request import RunRequest, RunReceipt


class TriggerPort(Protocol):
    def start_run(self, request: RunRequest) -> RunReceipt:
        ...
