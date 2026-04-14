from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid

from src.kernel.event_priority import EventPriority


@dataclass(frozen=True)
class Event:
    type: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    priority: EventPriority = EventPriority.P2
    run_id: str | None = None
    context_id: str | None = None
    correlation_id: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
