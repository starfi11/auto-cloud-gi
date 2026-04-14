from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiagnosticHint:
    code: str
    category: str
    hint: str


def classify_failure(detail: str) -> DiagnosticHint:
    d = (detail or "").lower()
    if "game_exe_not_configured" in d or "assistant_exe_not_configured" in d:
        return DiagnosticHint("CFG_MISSING_EXE", "configuration", "配置缺少可执行文件路径")
    if "winerror 2" in d or "file not found" in d or "系统找不到指定的文件" in d:
        return DiagnosticHint("PATH_NOT_FOUND", "configuration", "检查 .env 里的 exe/log 路径是否存在")
    if "resource_acquire_timeout" in d:
        return DiagnosticHint("RESOURCE_TIMEOUT", "runtime", "资源锁超时，检查是否有并发占用")
    if "window_not_foreground" in d or "focus_lost" in d:
        return DiagnosticHint("FOCUS_LOST", "ui", "窗口未聚焦，检查前台窗口与分辨率")
    if "ready_text_timeout" in d or "wait_scene_timeout" in d:
        return DiagnosticHint("WAIT_TIMEOUT", "flow", "等待超时，检查识别条件或延长超时")
    if "log_idle_timeout" in d:
        return DiagnosticHint("ASSISTANT_TIMEOUT", "assistant", "BetterGI 日志未进入静默，检查日志路径/任务状态")
    if "risk_stop:" in d:
        return DiagnosticHint("RISK_STOP", "safety", "触发风控停止，查看 risk 事件")
    if "interrupted:" in d:
        return DiagnosticHint("INTERRUPTED", "control", "收到中断信号")
    return DiagnosticHint("UNKNOWN", "unknown", "查看 actions/events/replay_trace 定位详细原因")
