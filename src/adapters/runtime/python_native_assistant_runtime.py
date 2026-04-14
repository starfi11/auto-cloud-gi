from __future__ import annotations

import os
import subprocess
from typing import Any

from src.adapters.action_specs import one_dragon_drive_macro
from src.adapters.runtime.log_watch import LogActivityWatcher, LogWatchSpec
from src.adapters.runtime.process_registry import ProcessRegistry
from src.adapters.runtime.ui_macro import UiMacroExecutor, build_ui_backend
from src.ports.assistant_runtime_port import AssistantRuntimePort


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class PythonNativeAssistantRuntimeAdapter(AssistantRuntimePort):
    def __init__(self) -> None:
        backend_mode = os.getenv("UI_AUTOMATION_BACKEND", "auto")
        self._macro = UiMacroExecutor(build_ui_backend(backend_mode))
        self._watcher = LogActivityWatcher()
        self._processes = ProcessRegistry()
        self._strict = _env_bool("PY_RUNTIME_STRICT", default=False)

    def launch(self, options: dict[str, Any]) -> dict[str, Any]:
        exe = str(options.get("assistant_exe") or os.getenv("BETTERGI_EXE", "")).strip()
        steps = list(options.get("launch_macro_steps", []))

        evidence_refs: list[str] = []
        if exe:
            try:
                proc = subprocess.Popen([exe], shell=False)
                mp = self._processes.register("assistant", proc)
                evidence_refs.append(f"exe:{exe}")
                evidence_refs.append(f"pid:{mp.pid}")
            except Exception as exc:
                return {
                    "ok": False,
                    "retryable": True,
                    "detail": f"assistant_launch_failed:{exc}",
                    "evidence_refs": [f"exe:{exe}"],
                }
        elif self._strict:
            return {
                "ok": False,
                "retryable": True,
                "detail": "assistant_exe_not_configured",
            }

        if steps:
            results = self._macro.execute(steps)
            failed = [r for r in results if not r.ok]
            evidence_refs.extend([f"macro:{r.detail}" for r in results[:3]])
            if failed:
                return {
                    "ok": False,
                    "retryable": True,
                    "detail": f"assistant_launch_macro_failed:{len(failed)}",
                    "macro_results": [r.__dict__ for r in results],
                    "evidence_refs": evidence_refs,
                }

        return {
            "ok": True,
            "retryable": False,
            "detail": "assistant_launch_done",
            "evidence_refs": evidence_refs,
            "process": self._processes.status("assistant"),
        }

    def drive(self, scenario: str, options: dict[str, Any]) -> dict[str, Any]:
        steps = list(options.get("drive_macro_steps", []))
        if not steps:
            steps = self._default_btgi_drive_macro()

        results = self._macro.execute(steps)
        failed = [r for r in results if not r.ok]
        if failed:
            return {
                "ok": False,
                "retryable": True,
                "detail": f"assistant_drive_macro_failed:{len(failed)}",
                "macro_results": [r.__dict__ for r in results],
                "scenario": scenario,
            }

        watch_root = str(
            options.get("assistant_log_root")
            or options.get("log_root")
            or os.getenv("BETTERGI_LOG_DIR", "")
        ).strip()
        watch_glob = str(options.get("assistant_log_glob") or os.getenv("BETTERGI_LOG_GLOB", "*.log")).strip()
        if watch_root:
            watch = self._watcher.wait_until_idle(
                LogWatchSpec(
                    root=watch_root,
                    glob=watch_glob or "*.log",
                    idle_seconds=float(options.get("assistant_idle_seconds", 45.0)),
                    timeout_seconds=float(options.get("assistant_timeout_seconds", 5400.0)),
                    poll_interval_seconds=float(options.get("assistant_poll_seconds", 1.0)),
                    require_activity=bool(options.get("assistant_require_log_activity", True)),
                )
            )
            if not watch.ok:
                return {
                    "ok": False,
                    "retryable": True,
                    "detail": watch.detail,
                    "scenario": scenario,
                    "evidence_refs": watch.watched_files[:3],
                    "watch_elapsed_seconds": watch.elapsed_seconds,
                }
            return {
                "ok": True,
                "retryable": False,
                "detail": "assistant_drive_finished_by_log_idle",
                "scenario": scenario,
                "evidence_refs": watch.watched_files[:3],
                "watch_elapsed_seconds": watch.elapsed_seconds,
                "log_changed_count": watch.changed_count,
            }

        return {
            "ok": True,
            "retryable": False,
            "detail": "assistant_drive_finished_no_log_watch",
            "scenario": scenario,
        }

    def collect(self, options: dict[str, Any]) -> dict[str, Any]:
        steps = list(options.get("collect_macro_steps", []))
        if not steps:
            return {
                "ok": True,
                "retryable": False,
                "detail": "collect_noop",
                "options": options,
            }
        results = self._macro.execute(steps)
        failed = [r for r in results if not r.ok]
        return {
            "ok": len(failed) == 0,
            "retryable": True if failed else False,
            "detail": "collect_macro_done" if not failed else f"collect_macro_failed:{len(failed)}",
            "macro_results": [r.__dict__ for r in results],
        }

    def stop(self) -> dict[str, Any]:
        status = self._processes.status("assistant")
        terminated = self._processes.terminate("assistant")
        return {
            "ok": bool(terminated.get("ok", True)),
            "retryable": False,
            "detail": str(terminated.get("detail", "assistant_stop_done")),
            "process_before_stop": status,
        }

    def _default_btgi_drive_macro(self) -> list[dict[str, Any]]:
        return one_dragon_drive_macro()
