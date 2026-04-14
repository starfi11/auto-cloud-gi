from __future__ import annotations

from typing import Protocol, Any, Callable


class GameRuntimePort(Protocol):
    def launch(self, options: dict[str, Any]) -> dict[str, Any]:
        ...

    def enter_queue(self, options: dict[str, Any]) -> dict[str, Any]:
        ...

    def wait_scene_ready(
        self,
        options: dict[str, Any],
        interrupt_check: Callable[[], tuple[bool, str]] | None = None,
        risk_check: Callable[[], tuple[bool, str]] | None = None,
    ) -> dict[str, Any]:
        ...

    def stop(self) -> dict[str, Any]:
        ...
