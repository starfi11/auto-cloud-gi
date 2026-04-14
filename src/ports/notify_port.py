from __future__ import annotations

from typing import Protocol


class NotifyPort(Protocol):
    def notify(self, title: str, body: str) -> None:
        ...
