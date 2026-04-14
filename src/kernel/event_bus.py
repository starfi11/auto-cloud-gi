from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from queue import PriorityQueue
import threading

from src.kernel.event_contract import Event

EventHandler = Callable[[Event], None]
EventHook = Callable[[Event], None]


class EventBus:
    def __init__(self, on_publish: EventHook | None = None, on_dispatch: EventHook | None = None) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._queue: PriorityQueue[tuple[int, str, Event]] = PriorityQueue()
        self._lock = threading.Lock()
        self._on_publish = on_publish
        self._on_dispatch = on_dispatch

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        with self._lock:
            self._handlers[event_type].append(handler)

    def publish(self, event: Event) -> None:
        self._queue.put((int(event.priority), event.event_id, event))
        if self._on_publish:
            self._on_publish(event)

    def dispatch_once(self) -> bool:
        if self._queue.empty():
            return False
        _, _, event = self._queue.get()
        if self._on_dispatch:
            self._on_dispatch(event)
        handlers = self._handlers.get(event.type, []) + self._handlers.get("*", [])
        for handler in handlers:
            handler(event)
        return True

    def drain(self) -> int:
        count = 0
        while self.dispatch_once():
            count += 1
        return count
