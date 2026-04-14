from __future__ import annotations

from typing import Protocol, Any


class AssistantRuntimePort(Protocol):
    def launch(self, options: dict[str, Any]) -> dict[str, Any]:
        ...

    def drive(self, scenario: str, options: dict[str, Any]) -> dict[str, Any]:
        ...

    def collect(self, options: dict[str, Any]) -> dict[str, Any]:
        ...

    def stop(self) -> dict[str, Any]:
        ...
