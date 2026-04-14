from __future__ import annotations

from typing import Protocol


class SchedulerPort(Protocol):
    def start_instance(self, instance_id: str) -> bool:
        ...

    def stop_instance(self, instance_id: str) -> bool:
        ...
