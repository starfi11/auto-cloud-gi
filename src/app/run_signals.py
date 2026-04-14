from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass
class RunSignalState:
    interrupted: bool = False
    interrupt_reason: str = ""
    risk_stopped: bool = False
    risk_reason: str = ""


class RunSignalCenter:
    def __init__(self) -> None:
        self._states: dict[str, RunSignalState] = {}
        self._lock = Lock()

    def init_run(self, run_id: str) -> None:
        with self._lock:
            self._states.setdefault(run_id, RunSignalState())

    def cleanup_run(self, run_id: str) -> None:
        with self._lock:
            self._states.pop(run_id, None)

    def interrupt(self, run_id: str, reason: str) -> bool:
        with self._lock:
            state = self._states.get(run_id)
            if state is None:
                return False
            state.interrupted = True
            state.interrupt_reason = reason
            return True

    def risk_stop(self, run_id: str, reason: str) -> bool:
        with self._lock:
            state = self._states.get(run_id)
            if state is None:
                return False
            state.risk_stopped = True
            state.risk_reason = reason
            return True

    def snapshot(self, run_id: str) -> RunSignalState:
        with self._lock:
            state = self._states.get(run_id)
            if state is None:
                return RunSignalState()
            return RunSignalState(
                interrupted=state.interrupted,
                interrupt_reason=state.interrupt_reason,
                risk_stopped=state.risk_stopped,
                risk_reason=state.risk_reason,
            )
