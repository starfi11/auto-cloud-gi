from __future__ import annotations

from typing import Protocol

from src.kernel.event_contract import Event


class EventSource(Protocol):
    def name(self) -> str:
        ...

    def poll(self) -> list[Event]:
        ...
