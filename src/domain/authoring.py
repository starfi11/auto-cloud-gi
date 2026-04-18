"""Authoring helpers that expand into ordinary domain objects.

The core execution layer (StateNode, Guard, ScenarioSpec) is intentionally
flat so the runtime stays simple. These helpers sit one level up and just
emit flat domain objects — the runtime never sees them. Purpose: cut the
boilerplate when a state has many phase-specific actions sharing the same
screen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.domain.blackboard import Guard
from src.domain.workflow import ActionIntent, StateNode


@dataclass(frozen=True)
class Phase:
    """One (guard, action) pair under a PhasedStateNode."""

    guard: Guard
    action: ActionIntent | None = None
    next_state: str | None = None


@dataclass(frozen=True)
class PhasedStateNode:
    """Declarative "same screen, different action per phase" node.

    Expands into N+1 StateNodes: one per phase (with the phase's guard),
    plus an optional unguarded fallback. Authors never have to hand-wire
    Guard instances into each action node.

    Example::

        phased = PhasedStateNode(
            state="S_MENU",
            phases=[
                Phase(Guard("current_goal", "eq", "daily"),
                      ActionIntent(name="click_daily", kind="ui.click"),
                      next_state="S_DAILY"),
                Phase(Guard("current_goal", "eq", "shop"),
                      ActionIntent(name="click_shop", kind="ui.click"),
                      next_state="S_SHOP"),
            ],
            fallback=ActionIntent(name="close", kind="ui.close"),
            fallback_next_state="S_DONE",
        )
        plan_nodes = phased.expand()
    """

    state: str
    phases: list[Phase] = field(default_factory=list)
    fallback: ActionIntent | None = None
    fallback_next_state: str | None = None
    wait_seconds: float = 0.2
    stable_ticks: int = 1
    recognition: dict[str, Any] = field(default_factory=dict)
    controller_id: str | None = None
    context_id: str | None = None
    expected_next: tuple[str, ...] | None = None
    recoverability: str = "transient"

    def expand(self) -> list[StateNode]:
        out: list[StateNode] = []
        for p in self.phases:
            out.append(
                StateNode(
                    state=self.state,
                    action=p.action,
                    next_state=p.next_state,
                    wait_seconds=self.wait_seconds,
                    stable_ticks=self.stable_ticks,
                    recognition=self.recognition,
                    controller_id=self.controller_id,
                    context_id=self.context_id,
                    expected_next=self.expected_next,
                    guard=p.guard,
                    recoverability=self.recoverability,
                )
            )
        if self.fallback is not None or self.fallback_next_state is not None:
            out.append(
                StateNode(
                    state=self.state,
                    action=self.fallback,
                    next_state=self.fallback_next_state,
                    wait_seconds=self.wait_seconds,
                    stable_ticks=self.stable_ticks,
                    recognition=self.recognition,
                    controller_id=self.controller_id,
                    context_id=self.context_id,
                    expected_next=self.expected_next,
                    guard=None,
                    recoverability=self.recoverability,
                )
            )
        return out
