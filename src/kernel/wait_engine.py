from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time

from src.kernel.event_contract import Event
from src.kernel.wait_conditions import WaitCondition
from src.kernel.timeout_manager import Timeout


@dataclass
class WaitResult:
    matched: bool
    reason: str
    events_seen: int
    fallback_used: bool = False


@dataclass
class WaitEngine:
    poll_interval_seconds: float = 0.2
    _cancel_event: threading.Event = field(default_factory=threading.Event)

    def cancel(self) -> None:
        self._cancel_event.set()

    def reset_cancel(self) -> None:
        self._cancel_event.clear()

    def wait_for(
        self,
        condition: WaitCondition,
        timeout_seconds: float,
        event_stream: list[Event],
        fallback_chain: list[WaitCondition] | None = None,
    ) -> WaitResult:
        timeout = Timeout.start(timeout_seconds)

        while True:
            if self._cancel_event.is_set():
                return WaitResult(False, "cancelled", len(event_stream))

            if condition.matched(event_stream):
                return WaitResult(True, "matched", len(event_stream))

            if timeout.is_expired():
                break

            time.sleep(self.poll_interval_seconds)

        if fallback_chain:
            for fb in fallback_chain:
                if fb.matched(event_stream):
                    return WaitResult(True, "matched_by_fallback", len(event_stream), fallback_used=True)

        return WaitResult(False, "timeout", len(event_stream))
