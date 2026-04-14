from __future__ import annotations

from typing import Protocol, Any


class InputPort(Protocol):
    def click(self, target_spec: dict[str, Any]) -> dict[str, Any]:
        ...
