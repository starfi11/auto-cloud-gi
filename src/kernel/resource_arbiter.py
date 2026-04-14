from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic, sleep
import uuid


@dataclass(frozen=True)
class ResourceLease:
    lease_id: str
    run_id: str
    resources: tuple[str, ...]


class ResourceArbiter:
    def __init__(self) -> None:
        self._lock = Lock()
        self._owners: dict[str, str] = {}

    def acquire(self, run_id: str, resources: list[str], timeout_seconds: float = 1.0) -> ResourceLease | None:
        wanted = tuple(sorted(set(r.strip() for r in resources if r.strip())))
        if not wanted:
            return ResourceLease(lease_id=f"no_lock:{uuid.uuid4()}", run_id=run_id, resources=())

        deadline = monotonic() + max(0.01, timeout_seconds)
        while monotonic() <= deadline:
            with self._lock:
                if all((res not in self._owners or self._owners[res] == run_id) for res in wanted):
                    lease_id = str(uuid.uuid4())
                    for res in wanted:
                        self._owners[res] = run_id
                    return ResourceLease(lease_id=lease_id, run_id=run_id, resources=wanted)
            sleep(0.01)
        return None

    def release(self, lease: ResourceLease) -> None:
        if not lease.resources:
            return
        with self._lock:
            for res in lease.resources:
                if self._owners.get(res) == lease.run_id:
                    self._owners.pop(res, None)
