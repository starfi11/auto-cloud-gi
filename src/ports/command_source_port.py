from __future__ import annotations

from typing import Protocol, Any


class CommandSourcePort(Protocol):
    def fetch_effective_overrides(self) -> dict[str, Any]:
        ...
