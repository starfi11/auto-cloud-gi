from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.kernel.event_contract import Event


class ConditionOp(str, Enum):
    ANY = "ANY"
    ALL = "ALL"
    SEQUENCE = "SEQUENCE"


@dataclass(frozen=True)
class EventPredicate:
    event_type: str

    def match(self, event: Event) -> bool:
        return event.type == self.event_type


@dataclass
class WaitCondition:
    op: ConditionOp
    predicates: list[EventPredicate]

    def matched(self, events: list[Event]) -> bool:
        if not self.predicates:
            return False

        if self.op == ConditionOp.ANY:
            return any(any(p.match(e) for e in events) for p in self.predicates)

        if self.op == ConditionOp.ALL:
            return all(any(p.match(e) for e in events) for p in self.predicates)

        # SEQUENCE
        idx = 0
        for event in events:
            if self.predicates[idx].match(event):
                idx += 1
                if idx >= len(self.predicates):
                    return True
        return False
