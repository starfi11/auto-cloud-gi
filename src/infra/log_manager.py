from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import os
from threading import Lock
from typing import Any


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return str(value)


class JsonlFileWriter:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    @property
    def path(self) -> Path:
        return self._path

    def append(self, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line)
                f.write("\n")


class RunLogBundle:
    def __init__(self, run_id: str, run_root: Path) -> None:
        self.run_id = run_id
        self.run_root = run_root
        self.events = JsonlFileWriter(run_root / "events.jsonl")
        self.transitions = JsonlFileWriter(run_root / "state_transitions.jsonl")
        self.actions = JsonlFileWriter(run_root / "actions.jsonl")
        self.replay = JsonlFileWriter(run_root / "replay_trace.jsonl")


class LogManager:
    def __init__(self, runtime_dir: str) -> None:
        self._root = Path(runtime_dir) / "logs"
        self._root.mkdir(parents=True, exist_ok=True)
        self._system = JsonlFileWriter(self._root / "system.jsonl")
        self._control_api = JsonlFileWriter(self._root / "control_api.jsonl")
        self._run_bundles: dict[str, RunLogBundle] = {}
        self._run_seq: dict[str, int] = {}
        self._lock = Lock()
        self._console_lock = Lock()
        self._console_enabled = os.getenv("LOG_CONSOLE_ENABLED", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._console_verbose = os.getenv("LOG_CONSOLE_VERBOSE", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._console_level = os.getenv("LOG_CONSOLE_LEVEL", "INFO").strip().upper()
        self._level_weight = {"DEBUG": 10, "INFO": 20, "WARN": 30, "WARNING": 30, "ERROR": 40, "FATAL": 50}

    @property
    def root(self) -> Path:
        return self._root

    def system_event(self, event_type: str, payload: dict[str, Any], level: str = "INFO") -> None:
        self._system.append(
            {
                "ts": utc_iso_now(),
                "level": level,
                "event_type": event_type,
                "payload": _json_safe(payload),
            }
        )
        self._console(
            level=level,
            message=f"[system] {event_type}",
            payload=payload if (self._console_verbose or level.upper() in {"WARN", "WARNING", "ERROR", "FATAL"}) else None,
        )

    def control_api_event(self, event_type: str, payload: dict[str, Any], level: str = "INFO") -> None:
        self._control_api.append(
            {
                "ts": utc_iso_now(),
                "level": level,
                "event_type": event_type,
                "payload": _json_safe(payload),
            }
        )
        self._console(
            level=level,
            message=f"[control-api] {event_type}",
            payload=payload if self._console_verbose else None,
        )

    def _ensure_run_bundle(self, run_id: str) -> RunLogBundle:
        with self._lock:
            bundle = self._run_bundles.get(run_id)
            if bundle is not None:
                return bundle
            run_root = self._root / "runs" / run_id
            bundle = RunLogBundle(run_id=run_id, run_root=run_root)
            self._run_bundles[run_id] = bundle
            self._run_seq.setdefault(run_id, 0)
            return bundle

    def _next_seq(self, run_id: str) -> int:
        with self._lock:
            current = self._run_seq.get(run_id, 0) + 1
            self._run_seq[run_id] = current
            return current

    def run_event(self, run_id: str, event_type: str, payload: dict[str, Any], level: str = "INFO") -> None:
        bundle = self._ensure_run_bundle(run_id)
        seq = self._next_seq(run_id)
        bundle.events.append(
            {
                "seq": seq,
                "ts": utc_iso_now(),
                "level": level,
                "run_id": run_id,
                "event_type": event_type,
                "payload": _json_safe(payload),
            }
        )
        if self._console_verbose or self._is_key_run_event(event_type, level):
            self._console(
                level=level,
                message=f"[run:{run_id}] {event_type}",
                payload=self._compact_payload_for_console(event_type, payload),
            )

    def state_transition(self, run_id: str, source: str, target: str, reason: str = "") -> None:
        bundle = self._ensure_run_bundle(run_id)
        seq = self._next_seq(run_id)
        bundle.transitions.append(
            {
                "seq": seq,
                "ts": utc_iso_now(),
                "run_id": run_id,
                "source": source,
                "target": target,
                "reason": reason,
            }
        )
        self._console(
            level="INFO",
            message=f"[run:{run_id}] transition {source} -> {target}",
            payload={"reason": reason},
        )

    def action_event(
        self,
        run_id: str,
        action_name: str,
        status: str,
        payload: dict[str, Any] | None = None,
        level: str = "INFO",
    ) -> None:
        bundle = self._ensure_run_bundle(run_id)
        seq = self._next_seq(run_id)
        bundle.actions.append(
            {
                "seq": seq,
                "ts": utc_iso_now(),
                "level": level,
                "run_id": run_id,
                "action": action_name,
                "status": status,
                "payload": _json_safe(payload or {}),
            }
        )
        if self._console_verbose or status in {"started", "retrying", "failed", "succeeded"} or level.upper() in {"WARN", "WARNING", "ERROR"}:
            self._console(
                level=level,
                message=f"[run:{run_id}] action {action_name} {status}",
                payload=self._compact_action_payload(payload or {}),
            )

    def write_run_summary(self, run_id: str, summary: dict[str, Any]) -> Path:
        bundle = self._ensure_run_bundle(run_id)
        path = bundle.run_root / "summary.json"
        path.write_text(json.dumps(_json_safe(summary), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_run_diagnostics(self, run_id: str, diagnostics: dict[str, Any]) -> Path:
        bundle = self._ensure_run_bundle(run_id)
        path = bundle.run_root / "diagnostics.json"
        path.write_text(json.dumps(_json_safe(diagnostics), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def replay_event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        bundle = self._ensure_run_bundle(run_id)
        seq = self._next_seq(run_id)
        bundle.replay.append(
            {
                "seq": seq,
                "ts": utc_iso_now(),
                "run_id": run_id,
                "event_type": event_type,
                "payload": _json_safe(payload),
            }
        )
        if self._console_verbose and event_type in {"sense", "decision", "transition_observe", "action_result"}:
            self._console(
                level="INFO",
                message=f"[run:{run_id}] replay {event_type}",
                payload=self._compact_payload_for_console(event_type, payload),
            )

    def _is_key_run_event(self, event_type: str, level: str) -> bool:
        if level.upper() in {"WARN", "WARNING", "ERROR", "FATAL"}:
            return True
        return event_type in {
            "policy_decision",
            "state_estimated",
            "transition_pending_set",
            "transition_pending_committed",
            "run_execution_failed",
            "run_execution_interrupted",
            "run_accepted",
            "run_rejected",
        }

    def _compact_action_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in ("kind", "attempt", "max_retries", "retryable", "elapsed_ms", "context_id", "controller_id", "detail"):
            if key in payload:
                out[key] = payload.get(key)
        result = payload.get("result")
        if isinstance(result, dict):
            out["result"] = {
                "ok": bool(result.get("ok", False)),
                "detail": str(result.get("detail", "")),
                "retryable": bool(result.get("retryable", True)),
            }
            macro_results = result.get("macro_results")
            if isinstance(macro_results, list) and macro_results:
                out["macro"] = [self._json_safe_macro_result(x) for x in macro_results[:6]]
        return out

    def _json_safe_macro_result(self, item: Any) -> dict[str, Any]:
        if not isinstance(item, dict):
            return {"raw": str(item)}
        return {
            "op": item.get("op"),
            "ok": item.get("ok"),
            "detail": item.get("detail"),
        }

    def _compact_payload_for_console(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        if event_type == "state_estimated":
            return {
                "tick": payload.get("tick"),
                "state": payload.get("state"),
                "confidence": payload.get("confidence"),
                "uncertainty_reason": payload.get("uncertainty_reason", ""),
                "candidates": payload.get("perception_candidates", [])[:4],
            }
        if event_type == "policy_decision":
            return {
                "tick": payload.get("tick"),
                "state": payload.get("state"),
                "kind": payload.get("kind"),
                "reason": payload.get("reason"),
                "next_state": payload.get("next_state"),
                "action": payload.get("action"),
                "wait_seconds": payload.get("wait_seconds"),
            }
        if event_type in {"run_execution_failed", "run_execution_interrupted"}:
            return {
                "error": payload.get("error", payload.get("reason", "")),
                "error_type": payload.get("error_type", ""),
            }
        return payload

    def _console(self, *, level: str, message: str, payload: dict[str, Any] | None) -> None:
        if not self._console_enabled:
            return
        if self._level_weight.get(level.upper(), 20) < self._level_weight.get(self._console_level, 20):
            return
        line = message
        if payload:
            line = f"{line} {json.dumps(_json_safe(payload), ensure_ascii=False, separators=(',', ':'))}"
        with self._console_lock:
            print(line, flush=True)
