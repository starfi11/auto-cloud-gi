from __future__ import annotations

import os
import subprocess
from time import monotonic, sleep
from typing import Any, Callable

from src.adapters.action_specs import cloud_queue_macro
from src.adapters.runtime.process_registry import ProcessRegistry
from src.adapters.vision import FileTextSignalSource, TextSignalWaiter, TextWaitSpec
from src.adapters.runtime.ui_macro import UiMacroExecutor, build_ui_backend
from src.ports.game_runtime_port import GameRuntimePort


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class PythonNativeGameRuntimeAdapter(GameRuntimePort):
    def __init__(self) -> None:
        backend_mode = os.getenv("UI_AUTOMATION_BACKEND", "auto")
        self._macro = UiMacroExecutor(build_ui_backend(backend_mode))
        self._text_waiter = TextSignalWaiter()
        self._processes = ProcessRegistry()
        self._strict = _env_bool("PY_RUNTIME_STRICT", default=False)

    def launch(self, options: dict[str, Any]) -> dict[str, Any]:
        exe = str(options.get("game_exe") or os.getenv("CLOUD_GI_EXE", "")).strip()
        if not exe:
            return {
                "ok": not self._strict,
                "retryable": True,
                "detail": "game_exe_not_configured",
            }
        try:
            proc = subprocess.Popen([exe], shell=False)
            mp = self._processes.register("game", proc)
            return {
                "ok": True,
                "retryable": False,
                "detail": "game_launch_started",
                "evidence_refs": [f"exe:{exe}", f"pid:{mp.pid}"],
                "process": self._processes.status("game"),
            }
        except Exception as exc:
            return {
                "ok": False,
                "retryable": True,
                "detail": f"game_launch_failed:{exc}",
                "evidence_refs": [f"exe:{exe}"],
            }

    def enter_queue(self, options: dict[str, Any]) -> dict[str, Any]:
        strategy = str(options.get("strategy", "normal")).strip().lower()
        steps = list(options.get("queue_macro_steps", []))
        if not steps:
            steps = self._default_queue_macro(strategy)

        results = self._macro.execute(steps)
        failed = [r for r in results if not r.ok]
        return {
            "ok": len(failed) == 0,
            "retryable": True,
            "detail": "queue_macro_done" if not failed else f"queue_macro_failed:{len(failed)}",
            "macro_results": [r.__dict__ for r in results],
        }

    def wait_scene_ready(
        self,
        options: dict[str, Any],
        interrupt_check: Callable[[], tuple[bool, str]] | None = None,
        risk_check: Callable[[], tuple[bool, str]] | None = None,
    ) -> dict[str, Any]:
        timeout_seconds = float(options.get("timeout_seconds", 180.0))
        ready_after_seconds = float(options.get("ready_after_seconds", 40.0))
        ready_flag_file = str(options.get("ready_flag_file", "")).strip()
        ready_text_any = [str(s) for s in options.get("scene_ready_text_any", [])]
        block_text_any = [str(s) for s in options.get("scene_block_text_any", [])]
        text_signal_file = str(
            options.get("text_signal_file") or os.getenv("VISION_TEXT_SIGNAL_FILE", "./runtime/vision/signals/latest.txt")
        ).strip()
        t0 = monotonic()

        if ready_text_any:
            text_result = self._text_waiter.wait_until_ready(
                FileTextSignalSource(path=text_signal_file),
                TextWaitSpec(
                    ready_any=ready_text_any,
                    block_any=block_text_any,
                    timeout_seconds=timeout_seconds,
                    poll_seconds=float(options.get("text_poll_seconds", 0.3)),
                ),
            )
            if not text_result.ok:
                return {
                    "ok": False,
                    "retryable": True,
                    "detail": text_result.detail,
                    "elapsed_seconds": text_result.elapsed_seconds,
                    "evidence_refs": [f"text_signal:{text_signal_file}"],
                }
            post = self._run_post_ready_macro(options)
            if post is not None:
                return post
            return {
                "ok": True,
                "retryable": False,
                "detail": "scene_ready_by_text_signal",
                "elapsed_seconds": text_result.elapsed_seconds,
                "evidence_refs": [f"text_signal:{text_signal_file}"],
                "matched_ready_text": text_result.matched_ready,
            }

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
            if ready_flag_file and os.path.exists(ready_flag_file):
                break
            if elapsed >= ready_after_seconds and not ready_flag_file:
                break
            if elapsed >= timeout_seconds:
                return {
                    "ok": False,
                    "retryable": True,
                    "detail": "wait_scene_timeout",
                    "elapsed_seconds": round(elapsed, 3),
                }
            sleep(0.2)

        post = self._run_post_ready_macro(options)
        if post is not None:
            return post

        return {
            "ok": True,
            "retryable": False,
            "detail": "scene_ready",
            "elapsed_seconds": round(monotonic() - t0, 3),
        }

    def stop(self) -> dict[str, Any]:
        status = self._processes.status("game")
        terminated = self._processes.terminate("game")
        return {
            "ok": bool(terminated.get("ok", True)),
            "retryable": False,
            "detail": str(terminated.get("detail", "game_stop_done")),
            "process_before_stop": status,
        }

    def _default_queue_macro(self, strategy: str) -> list[dict[str, Any]]:
        return cloud_queue_macro(strategy)

    def _run_post_ready_macro(self, options: dict[str, Any]) -> dict[str, Any] | None:
        post_steps = list(options.get("post_ready_macro_steps", []))
        if not post_steps:
            return None
        post_results = self._macro.execute(post_steps)
        failed = [r for r in post_results if not r.ok]
        if failed:
            return {
                "ok": False,
                "retryable": True,
                "detail": f"post_ready_macro_failed:{len(failed)}",
                "macro_results": [r.__dict__ for r in post_results],
            }
        return None
