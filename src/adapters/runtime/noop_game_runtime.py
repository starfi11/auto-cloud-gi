from __future__ import annotations

from time import monotonic, sleep
from typing import Any, Callable

from src.ports.game_runtime_port import GameRuntimePort


class NoopGameRuntimeAdapter(GameRuntimePort):
    def launch(self, options: dict[str, Any]) -> dict[str, Any]:
        sleep(0.01)
        return {"ok": True, "detail": "noop_game_launch", "options": options}

    def enter_queue(self, options: dict[str, Any]) -> dict[str, Any]:
        sleep(0.01)
        return {"ok": True, "detail": "noop_enter_queue", "options": options}

    def wait_scene_ready(
        self,
        options: dict[str, Any],
        interrupt_check: Callable[[], tuple[bool, str]] | None = None,
        risk_check: Callable[[], tuple[bool, str]] | None = None,
    ) -> dict[str, Any]:
        timeout_seconds = float(options.get("timeout_seconds", 8.0))
        ready_after_seconds = float(options.get("ready_after_seconds", 0.2))
        t0 = monotonic()
        while True:
            if risk_check is not None:
                hit, reason = risk_check()
                if hit:
                    return {
                        "ok": False,
                        "retryable": False,
                        "risk_stopped": True,
                        "detail": f"risk_stop:{reason or 'risk_detected'}",
                    }
            if interrupt_check is not None:
                hit, reason = interrupt_check()
                if hit:
                    return {
                        "ok": False,
                        "retryable": False,
                        "interrupted": True,
                        "detail": f"interrupted:{reason or 'manual_interrupt'}",
                    }
            elapsed = monotonic() - t0
            if elapsed >= ready_after_seconds:
                return {"ok": True, "detail": "noop_scene_ready", "elapsed_seconds": round(elapsed, 3)}
            if elapsed >= timeout_seconds:
                return {"ok": False, "detail": "noop_scene_timeout", "elapsed_seconds": round(elapsed, 3)}
            sleep(0.05)

    def stop(self) -> dict[str, Any]:
        return {"ok": True, "detail": "noop_game_stop"}
