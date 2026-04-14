from __future__ import annotations

from src.domain.run_request import RunRequest, RunReceipt
from src.ports.trigger_port import TriggerPort


class ControlApiAdapter:
    def __init__(self, trigger_port: TriggerPort) -> None:
        self._trigger = trigger_port

    def submit(self, request: RunRequest) -> RunReceipt:
        return self._trigger.start_run(request)
