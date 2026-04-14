from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from src.domain.layered_state import LayeredRuntimeState


@dataclass
class RunContext:
    run_id: str
    manifest: dict[str, Any]
    state: str = "BOOTSTRAP"
    active_context_id: str = "global"
    context_stack: list[str] = field(default_factory=lambda: ["global"])
    retries: dict[str, int] = field(default_factory=dict)
    event_cursor: int = 0
    artifacts: list[str] = field(default_factory=list)
    layered_state: LayeredRuntimeState = field(default_factory=LayeredRuntimeState)
    last_error: dict[str, Any] = field(default_factory=dict)


class ContextStore:
    def __init__(self) -> None:
        self._data: dict[str, RunContext] = {}
        self._lock = Lock()

    def put(self, context: RunContext) -> None:
        with self._lock:
            self._data[context.run_id] = context

    def get(self, run_id: str) -> RunContext | None:
        with self._lock:
            return self._data.get(run_id)

    def update_state(self, run_id: str, state: str) -> None:
        with self._lock:
            ctx = self._data.get(run_id)
            if not ctx:
                return
            ctx.state = state
