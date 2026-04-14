from __future__ import annotations

from collections.abc import Callable

TransitionHook = Callable[[str, str], None]


class StateMachine:
    def __init__(self, initial_state: str) -> None:
        self._state = initial_state
        self._transitions: dict[tuple[str, str], str] = {}
        self._hooks: list[TransitionHook] = []

    @property
    def state(self) -> str:
        return self._state

    def on_transition(self, hook: TransitionHook) -> None:
        self._hooks.append(hook)

    def allow(self, source: str, event: str, target: str) -> None:
        self._transitions[(source, event)] = target

    def trigger(self, event: str) -> str:
        key = (self._state, event)
        if key not in self._transitions:
            raise ValueError(f"transition not allowed: {key}")
        prev = self._state
        self._state = self._transitions[key]
        for hook in self._hooks:
            hook(prev, self._state)
        return self._state
