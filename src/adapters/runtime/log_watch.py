from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import monotonic, sleep
from typing import Callable


InterruptProbe = Callable[[], tuple[bool, str]]


@dataclass(frozen=True)
class LogWatchSpec:
    root: str
    glob: str = "*.log"
    idle_seconds: float = 30.0
    timeout_seconds: float = 1800.0
    poll_interval_seconds: float = 1.0
    require_activity: bool = True


@dataclass(frozen=True)
class LogWatchResult:
    ok: bool
    detail: str
    watched_files: list[str]
    changed_count: int
    elapsed_seconds: float


class LogActivityWatcher:
    def wait_until_idle(
        self,
        spec: LogWatchSpec,
        *,
        interrupt_check: InterruptProbe | None = None,
        risk_check: InterruptProbe | None = None,
    ) -> LogWatchResult:
        root = Path(spec.root)
        t0 = monotonic()
        last_change = monotonic()
        changed_count = 0
        seen_activity = False

        prev = self._snapshot(root, spec.glob)
        if prev:
            seen_activity = True

        while True:
            if risk_check is not None:
                hit, reason = risk_check()
                if hit:
                    return LogWatchResult(
                        ok=False,
                        detail=f"risk_stop:{reason or 'risk_detected'}",
                        watched_files=sorted(prev.keys()),
                        changed_count=changed_count,
                        elapsed_seconds=round(monotonic() - t0, 3),
                    )
            if interrupt_check is not None:
                hit, reason = interrupt_check()
                if hit:
                    return LogWatchResult(
                        ok=False,
                        detail=f"interrupted:{reason or 'manual_interrupt'}",
                        watched_files=sorted(prev.keys()),
                        changed_count=changed_count,
                        elapsed_seconds=round(monotonic() - t0, 3),
                    )

            now_snap = self._snapshot(root, spec.glob)
            if now_snap != prev:
                changed_count += 1
                seen_activity = True
                last_change = monotonic()
                prev = now_snap

            idle_for = monotonic() - last_change
            elapsed = monotonic() - t0
            if elapsed >= spec.timeout_seconds:
                return LogWatchResult(
                    ok=False,
                    detail="log_idle_timeout",
                    watched_files=sorted(prev.keys()),
                    changed_count=changed_count,
                    elapsed_seconds=round(elapsed, 3),
                )

            if idle_for >= spec.idle_seconds:
                if spec.require_activity and not seen_activity:
                    sleep(max(0.05, spec.poll_interval_seconds))
                    continue
                return LogWatchResult(
                    ok=True,
                    detail="log_idle_reached",
                    watched_files=sorted(prev.keys()),
                    changed_count=changed_count,
                    elapsed_seconds=round(elapsed, 3),
                )

            sleep(max(0.05, spec.poll_interval_seconds))

    def _snapshot(self, root: Path, glob_pattern: str) -> dict[str, tuple[int, int]]:
        snap: dict[str, tuple[int, int]] = {}
        if not root.exists():
            return snap
        for p in root.glob(glob_pattern):
            if not p.is_file():
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            snap[str(p)] = (int(st.st_size), int(st.st_mtime_ns))
        return snap
