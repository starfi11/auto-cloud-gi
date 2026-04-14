from __future__ import annotations

from dataclasses import dataclass
import subprocess
from typing import Any


@dataclass
class ManagedProcess:
    name: str
    popen: subprocess.Popen[Any]

    @property
    def pid(self) -> int:
        return int(self.popen.pid or 0)

    @property
    def running(self) -> bool:
        return self.popen.poll() is None


class ProcessRegistry:
    def __init__(self) -> None:
        self._data: dict[str, ManagedProcess] = {}

    def register(self, name: str, process: subprocess.Popen[Any]) -> ManagedProcess:
        mp = ManagedProcess(name=name, popen=process)
        self._data[name] = mp
        return mp

    def get(self, name: str) -> ManagedProcess | None:
        return self._data.get(name)

    def status(self, name: str) -> dict[str, object]:
        proc = self._data.get(name)
        if proc is None:
            return {"exists": False, "running": False, "pid": 0}
        return {"exists": True, "running": proc.running, "pid": proc.pid}

    def terminate(self, name: str) -> dict[str, object]:
        proc = self._data.get(name)
        if proc is None:
            return {"ok": True, "detail": "process_not_found"}
        if proc.running:
            try:
                proc.popen.terminate()
            except Exception as exc:
                return {"ok": False, "detail": f"terminate_failed:{exc}", "pid": proc.pid}
        return {"ok": True, "detail": "process_terminated", "pid": proc.pid}
