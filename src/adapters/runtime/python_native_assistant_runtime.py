from __future__ import annotations

import ctypes
import os
import subprocess
import time
from typing import Any

from src.adapters.action_specs import one_dragon_drive_macro
from src.adapters.drivers import BetterGiDriver
from src.adapters.runtime.log_watch import LogActivityWatcher, LogWatchSpec
from src.adapters.runtime.process_registry import ProcessRegistry
from src.adapters.runtime.ui_macro import UiMacroExecutor, build_ui_backend
from src.ports.assistant_runtime_port import AssistantRuntimePort


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _activate_window_windows(
    *,
    pid: int = 0,
    title_keywords: tuple[str, ...] = (),
    timeout_seconds: float = 2.5,
) -> tuple[bool, str]:
    if os.name != "nt":
        return True, "non_windows_skip"
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    get_window_text_length = user32.GetWindowTextLengthW
    get_window_text = user32.GetWindowTextW
    is_window_visible = user32.IsWindowVisible
    enum_windows = user32.EnumWindows
    get_window_thread_process_id = user32.GetWindowThreadProcessId
    show_window = user32.ShowWindow
    set_foreground_window = user32.SetForegroundWindow
    bring_window_to_top = user32.BringWindowToTop
    get_foreground_window = user32.GetForegroundWindow
    attach_thread_input = user32.AttachThreadInput
    get_current_thread_id = kernel32.GetCurrentThreadId
    get_window_thread_process_id.restype = ctypes.c_uint
    SW_RESTORE = 9

    wanted_keywords = tuple(k.lower() for k in title_keywords if k.strip())
    deadline = time.monotonic() + max(0.5, float(timeout_seconds))
    last_detail = "window_not_found"

    while time.monotonic() <= deadline:
        candidates: list[tuple[int, str, int]] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _enum_cb(hwnd, _lparam):
            try:
                if not is_window_visible(hwnd):
                    return True
                title_len = int(get_window_text_length(hwnd))
                if title_len <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(title_len + 1)
                get_window_text(hwnd, buf, title_len + 1)
                title = str(buf.value or "").strip()
                if not title:
                    return True
                pid_ref = ctypes.c_uint(0)
                get_window_thread_process_id(hwnd, ctypes.byref(pid_ref))
                win_pid = int(pid_ref.value)
                title_l = title.lower()
                title_ok = (not wanted_keywords) or any(k in title_l for k in wanted_keywords)
                pid_ok = (pid <= 0) or (win_pid == pid)
                if title_ok and pid_ok:
                    candidates.append((int(hwnd), title, win_pid))
            except Exception:
                return True
            return True

        enum_windows(_enum_cb, 0)
        if not candidates:
            last_detail = "window_not_found"
            time.sleep(0.2)
            continue

        for hwnd, title, win_pid in candidates:
            try:
                show_window(hwnd, SW_RESTORE)
                bring_window_to_top(hwnd)
                fg = int(get_foreground_window())
                fg_tid = int(get_window_thread_process_id(fg, None)) if fg else 0
                target_tid = int(get_window_thread_process_id(hwnd, None))
                current_tid = int(get_current_thread_id())
                if fg_tid and target_tid and fg_tid != current_tid:
                    attach_thread_input(current_tid, fg_tid, True)
                    attach_thread_input(current_tid, target_tid, True)
                set_foreground_window(hwnd)
                if fg_tid and target_tid and fg_tid != current_tid:
                    attach_thread_input(current_tid, target_tid, False)
                    attach_thread_input(current_tid, fg_tid, False)
                time.sleep(0.08)
                current_fg = int(get_foreground_window())
                if current_fg == hwnd:
                    return True, f"window_activated:{title}:{win_pid}"
                last_detail = f"window_not_foreground:{title}:{win_pid}"
            except Exception as exc:
                last_detail = f"window_activate_error:{type(exc).__name__}:{exc}"
        time.sleep(0.2)
    return False, last_detail


class PythonNativeAssistantRuntimeAdapter(AssistantRuntimePort):
    def __init__(self) -> None:
        backend_mode = os.getenv("UI_AUTOMATION_BACKEND", "auto")
        self._macro = UiMacroExecutor(build_ui_backend(backend_mode))
        self._driver = BetterGiDriver(self._macro)
        self._watcher = LogActivityWatcher()
        self._processes = ProcessRegistry()
        self._strict = _env_bool("PY_RUNTIME_STRICT", default=False)

    def launch(self, options: dict[str, Any]) -> dict[str, Any]:
        exe = str(options.get("assistant_exe") or os.getenv("BETTERGI_EXE", "")).strip()
        steps = list(options.get("launch_macro_steps", []))
        skip_start = bool(options.get("skip_start_process", False))
        evidence_refs: list[str] = []
        if skip_start:
            pass
        elif exe:
            try:
                proc = subprocess.Popen([exe], shell=False)
                mp = self._processes.register("assistant", proc)
                evidence_refs.append(f"exe:{exe}")
                evidence_refs.append(f"pid:{mp.pid}")
                launch_wait = float(
                    options.get("assistant_launch_wait_seconds")
                    or os.getenv("BETTERGI_LAUNCH_WAIT_SECONDS", "15")
                )
                if launch_wait > 0:
                    time.sleep(max(0.0, launch_wait))
                    evidence_refs.append(f"launch_wait:{round(launch_wait, 2)}s")
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
            r = self._driver.dismiss_update_if_present(steps)
            mr = list(r.get("macro_results", []))
            evidence_refs.extend([f"macro:{x.get('detail', '')}" for x in mr[:3] if isinstance(x, dict)])
            if not bool(r.get("ok", False)):
                return {
                    "ok": False,
                    "retryable": True,
                    "detail": str(r.get("detail", "assistant_launch_macro_failed")),
                    "macro_results": mr,
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
        r = self._driver.configure_and_start_one_dragon(steps=(steps or None))
        if not bool(r.get("ok", False)):
            return {
                "ok": False,
                "retryable": True,
                "detail": str(r.get("detail", "assistant_drive_macro_failed")),
                "macro_results": list(r.get("macro_results", [])),
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
