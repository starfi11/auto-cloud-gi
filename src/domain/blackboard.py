"""Run-scoped mutable key/value store + guard predicate.

The Blackboard holds cross-tick memory so the state machine can represent
"which phase / how many times" without putting that state in the screen.

A Guard is a small predicate a ``StateNode`` may carry so that multiple
nodes sharing the same ``state`` name can be disambiguated by blackboard
content — e.g. ``S_MAIN_MENU[current_goal=="daily"]`` vs
``S_MAIN_MENU[current_goal=="shop"]``.

Guard evaluation is intentionally trivial (one key, one op); compound
guards can be layered later if the need shows up.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


_SUPPORTED_OPS: frozenset[str] = frozenset(
    {"eq", "ne", "lt", "le", "gt", "ge", "in", "not_in", "truthy", "falsy", "missing", "present"}
)


@dataclass(frozen=True)
class Guard:
    """Predicate evaluated against a Blackboard.

    ``op`` ∈ {eq, ne, lt, le, gt, ge, in, not_in, truthy, falsy, missing, present}.
    ``value`` is ignored for truthy/falsy/missing/present.
    """

    key: str
    op: str = "truthy"
    value: Any = None

    def __post_init__(self) -> None:  # pragma: no cover - validation helper
        if self.op not in _SUPPORTED_OPS:
            raise ValueError(f"guard op {self.op!r} not in {sorted(_SUPPORTED_OPS)}")
        if not self.key:
            raise ValueError("guard.key must be non-empty")


class Blackboard:
    """Run-scoped mutable KV. Single-threaded per run; no internal lock.

    ``version`` bumps on every mutation so callers can cheaply detect
    whether a snapshot is stale. ``snapshot()`` returns a deep copy safe
    for checkpoint / transport.
    """

    __slots__ = ("_data", "_version")

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(data) if data else {}
        self._version: int = 0

    # -- read ----------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def has(self, key: str) -> bool:
        return key in self._data

    def keys(self) -> Iterable[str]:
        return self._data.keys()

    @property
    def version(self) -> int:
        return self._version

    def snapshot(self) -> dict[str, Any]:
        import copy

        return copy.deepcopy(self._data)

    # -- write ---------------------------------------------------------

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._version += 1

    def delete(self, key: str) -> None:
        if key in self._data:
            del self._data[key]
            self._version += 1

    def inc(self, key: str, delta: int | float = 1) -> int | float:
        current = self._data.get(key, 0)
        if not isinstance(current, (int, float)) or isinstance(current, bool):
            raise TypeError(
                f"blackboard.inc target {key!r} is not numeric (got {type(current).__name__})"
            )
        new_value = current + delta
        self._data[key] = new_value
        self._version += 1
        return new_value

    def update(self, patch: dict[str, Any]) -> None:
        if not patch:
            return
        self._data.update(patch)
        self._version += 1

    def clear(self) -> None:
        if self._data:
            self._data.clear()
            self._version += 1


def evaluate_guard(guard: Guard | None, blackboard: Blackboard | None) -> bool:
    """Return True when ``guard`` is satisfied against ``blackboard``.

    Contract:
      - ``guard is None``: always True. Unguarded nodes match unconditionally.
      - ``blackboard is None`` with a non-None guard: treat as absent key —
        only ``op="missing"`` would pass; everything else fails.
    """
    if guard is None:
        return True
    if blackboard is None:
        return guard.op == "missing"

    has = blackboard.has(guard.key)
    actual = blackboard.get(guard.key) if has else None
    op = guard.op
    value = guard.value

    if op == "missing":
        return not has
    if op == "present":
        return has

    # All other ops require the key to exist, otherwise the predicate is
    # vacuously false — avoids accidental matches on unset counters.
    if not has:
        return False

    if op == "truthy":
        return bool(actual)
    if op == "falsy":
        return not bool(actual)
    if op == "eq":
        return actual == value
    if op == "ne":
        return actual != value
    if op == "in":
        try:
            return actual in value  # type: ignore[operator]
        except TypeError:
            return False
    if op == "not_in":
        try:
            return actual not in value  # type: ignore[operator]
        except TypeError:
            return False
    # Numeric comparisons — guard against non-comparable pairs.
    try:
        if op == "lt":
            return actual < value  # type: ignore[operator]
        if op == "le":
            return actual <= value  # type: ignore[operator]
        if op == "gt":
            return actual > value  # type: ignore[operator]
        if op == "ge":
            return actual >= value  # type: ignore[operator]
    except TypeError:
        return False
    return False


def guard_from_dict(payload: dict[str, Any] | None) -> Guard | None:
    if not payload:
        return None
    key = payload.get("key")
    if not isinstance(key, str) or not key:
        return None
    op = payload.get("op", "truthy")
    if op not in _SUPPORTED_OPS:
        return None
    return Guard(key=key, op=str(op), value=payload.get("value"))


def guard_to_dict(guard: Guard | None) -> dict[str, Any] | None:
    if guard is None:
        return None
    out: dict[str, Any] = {"key": guard.key, "op": guard.op}
    if guard.value is not None:
        out["value"] = guard.value
    return out
