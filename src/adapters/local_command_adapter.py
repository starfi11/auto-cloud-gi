from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any

from src.ports.command_source_port import CommandSourcePort


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # accept trailing Z
        fixed = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(fixed)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


class LocalFileCommandAdapter(CommandSourcePort):
    def __init__(self, file_path: str) -> None:
        self._path = Path(file_path)

    def fetch_effective_overrides(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}

        # Legacy shortcut format
        direct_overrides = payload.get("overrides", {})
        if isinstance(direct_overrides, dict) and direct_overrides:
            return dict(direct_overrides)

        # New extensible format
        commands = payload.get("commands", [])
        if not isinstance(commands, list):
            return {}

        now = datetime.now(timezone.utc)
        selected: dict[str, tuple[int, datetime, Any]] = {}

        for item in commands:
            if not isinstance(item, dict):
                continue
            if item.get("enabled", True) is False:
                continue

            key = item.get("key")
            if not isinstance(key, str) or not key:
                continue

            expires_at = _parse_dt(item.get("expires_at"))
            if expires_at is not None and expires_at <= now:
                continue

            priority = int(item.get("priority", 0))
            created_at = _parse_dt(item.get("created_at")) or datetime(1970, 1, 1, tzinfo=timezone.utc)
            value = item.get("value")

            current = selected.get(key)
            if current is None:
                selected[key] = (priority, created_at, value)
                continue

            cur_priority, cur_created, _ = current
            if priority > cur_priority or (priority == cur_priority and created_at > cur_created):
                selected[key] = (priority, created_at, value)

        return {k: v[2] for k, v in selected.items()}
