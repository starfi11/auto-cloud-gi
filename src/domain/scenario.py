"""Declarative goal-sequence spec that drives the state machine via blackboard.

A scenario is the thin "串行逻辑" layer above the state graph: it says
"do goal A until <blackboard>-says-it's-done, then goal B, then goal C".
Goals are not states — they're blackboard values (``current_goal``) that
Guards on StateNodes branch off. The state machine still owns transitions;
the scenario only advances when a goal's ``until`` guard passes.

This keeps application-layer logic as pure data: profile authors emit a
``ScenarioSpec`` plus a ``StatePlan``, and the runner wires them together.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.domain.blackboard import (
    Blackboard,
    Guard,
    evaluate_guard,
    guard_from_dict,
    guard_to_dict,
)


_GOAL_KEY = "current_goal"
_DONE_FLAG = "_scenario_done"


@dataclass(frozen=True)
class Goal:
    """One step in a scenario.

    - ``name`` lands in ``blackboard['current_goal']`` while this goal is active.
    - ``until`` is the guard that, when satisfied, advances to the next goal.
      ``None`` means "one-shot goal" — the runner advances immediately after
      the goal is installed. Useful for goals whose state plan has a natural
      terminal-ish exit, when authors don't have a clean signal to check.
    """

    name: str
    until: Guard | None = None

    def __post_init__(self) -> None:  # pragma: no cover
        if not self.name:
            raise ValueError("goal.name must be non-empty")


@dataclass(frozen=True)
class ScenarioSpec:
    name: str
    goals: list[Goal] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "goals": [
                {"name": g.name, "until": guard_to_dict(g.until)}
                for g in self.goals
            ],
        }

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> ScenarioSpec:
        raw_goals = payload.get("goals") or []
        goals: list[Goal] = []
        for rg in raw_goals:
            if not isinstance(rg, dict):
                continue
            name = rg.get("name")
            if not isinstance(name, str) or not name:
                continue
            until = guard_from_dict(rg.get("until")) if isinstance(rg.get("until"), dict) else None
            goals.append(Goal(name=name, until=until))
        return ScenarioSpec(name=str(payload.get("name", "")), goals=goals)


def advance_scenario(spec: ScenarioSpec, blackboard: Blackboard) -> str | None:
    """Install / advance the scenario against ``blackboard``.

    Returns the name of the currently-active goal after this call, or
    ``None`` when the scenario has run to completion. The blackboard state
    this touches:

    - ``current_goal``  → string, installed when entering a goal
    - ``_scenario_done`` → True once the last goal's until passes

    Call this at the top of every tick. It's idempotent when no guard
    change has happened since the last call.
    """
    if not spec.goals:
        blackboard.delete(_GOAL_KEY)
        blackboard.set(_DONE_FLAG, True)
        return None

    if blackboard.get(_DONE_FLAG) is True:
        return None

    current = blackboard.get(_GOAL_KEY)
    # Find the index of the current goal. If current isn't in spec.goals
    # (initial call, or blackboard was cleared), install the first.
    idx = _index_of(spec.goals, current) if isinstance(current, str) else -1
    if idx < 0:
        first = spec.goals[0]
        blackboard.set(_GOAL_KEY, first.name)
        # If the first goal is already satisfied (e.g. until-check passes
        # on fresh blackboard), fall through to advance immediately.
        idx = 0

    # Walk forward as long as the current goal's until is satisfied.
    while idx < len(spec.goals):
        goal = spec.goals[idx]
        if goal.until is None:
            # One-shot: advance immediately. Authors who want a single goal
            # to persist should supply an until that's initially false.
            idx += 1
            continue
        if evaluate_guard(goal.until, blackboard):
            idx += 1
            continue
        # Active goal found. Make sure it's written.
        if blackboard.get(_GOAL_KEY) != goal.name:
            blackboard.set(_GOAL_KEY, goal.name)
        return goal.name

    blackboard.set(_DONE_FLAG, True)
    blackboard.delete(_GOAL_KEY)
    return None


def _index_of(goals: list[Goal], name: str) -> int:
    for i, g in enumerate(goals):
        if g.name == name:
            return i
    return -1
