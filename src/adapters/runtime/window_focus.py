from __future__ import annotations

import ctypes
import os
import time


def activate_window(
    *,
    pid: int = 0,
    title_keywords: tuple[str, ...] = (),
    timeout_seconds: float = 2.5,
) -> tuple[bool, str]:
    if os.name != "nt":
        return True, "non_windows_skip"
    ok, detail = _activate_window_pywin32(
        pid=pid,
        title_keywords=title_keywords,
        timeout_seconds=timeout_seconds,
    )
    if ok:
        return ok, detail
    # Fallback for environments where pywin32 is missing/incompatible.
    ok2, detail2 = _activate_window_ctypes(
        pid=pid,
        title_keywords=title_keywords,
        timeout_seconds=timeout_seconds,
    )
    if ok2:
        return ok2, detail2
    return False, f"{detail};fallback:{detail2}"


def _activate_window_pywin32(
    *,
    pid: int = 0,
    title_keywords: tuple[str, ...] = (),
    timeout_seconds: float = 2.5,
) -> tuple[bool, str]:
    try:
        import win32api
        import win32con
        import win32gui
        import win32process
    except Exception as exc:
        return False, f"pywin32_unavailable:{type(exc).__name__}:{exc}"

    wanted_keywords = tuple(k.lower() for k in title_keywords if k.strip())
    deadline = time.monotonic() + max(0.5, float(timeout_seconds))
    last_detail = "window_not_found"

    while time.monotonic() <= deadline:
        candidates: list[tuple[int, str, int]] = []

        def _enum_cb(hwnd, _lparam):
            nonlocal candidates
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                title = str(win32gui.GetWindowText(hwnd) or "").strip()
                if not title:
                    return True
                _tid, win_pid = win32process.GetWindowThreadProcessId(hwnd)
                title_ok = (not wanted_keywords) or any(k in title.lower() for k in wanted_keywords)
                pid_ok = (pid <= 0) or (int(win_pid) == int(pid))
                if title_ok and pid_ok:
                    candidates.append((int(hwnd), title, int(win_pid)))
            except Exception:
                return True
            return True

        try:
            win32gui.EnumWindows(_enum_cb, 0)
        except Exception as exc:
            return False, f"enum_failed:{type(exc).__name__}:{exc}"

        if not candidates:
            last_detail = "window_not_found"
            time.sleep(0.2)
            continue

        for hwnd, title, win_pid in candidates:
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.BringWindowToTop(hwnd)
                fg_hwnd = int(win32gui.GetForegroundWindow() or 0)
                fg_tid = int(win32process.GetWindowThreadProcessId(fg_hwnd)[0]) if fg_hwnd else 0
                target_tid = int(win32process.GetWindowThreadProcessId(hwnd)[0])
                current_tid = int(win32api.GetCurrentThreadId())
                if fg_tid and target_tid and fg_tid != current_tid:
                    ctypes.windll.user32.AttachThreadInput(current_tid, fg_tid, True)  # type: ignore[attr-defined]
                    ctypes.windll.user32.AttachThreadInput(current_tid, target_tid, True)  # type: ignore[attr-defined]
                win32gui.SetForegroundWindow(hwnd)
                if fg_tid and target_tid and fg_tid != current_tid:
                    ctypes.windll.user32.AttachThreadInput(current_tid, target_tid, False)  # type: ignore[attr-defined]
                    ctypes.windll.user32.AttachThreadInput(current_tid, fg_tid, False)  # type: ignore[attr-defined]
                time.sleep(0.08)
                current_fg = int(win32gui.GetForegroundWindow() or 0)
                if current_fg == hwnd:
                    return True, f"window_activated:{title}:{win_pid}"
                last_detail = f"window_not_foreground:{title}:{win_pid}"
            except Exception as exc:
                last_detail = f"window_activate_error:{type(exc).__name__}:{exc}"
        time.sleep(0.2)
    return False, last_detail


def _activate_window_ctypes(
    *,
    pid: int = 0,
    title_keywords: tuple[str, ...] = (),
    timeout_seconds: float = 2.5,
) -> tuple[bool, str]:
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
