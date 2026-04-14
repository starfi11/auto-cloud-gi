from __future__ import annotations

from pathlib import Path
import json
from dataclasses import asdict, is_dataclass

from src.kernel.context_store import RunContext


class CheckpointStore:
    def __init__(self, runtime_dir: str) -> None:
        self._root = Path(runtime_dir) / "checkpoints"
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, context: RunContext) -> Path:
        path = self._root / f"{context.run_id}.json"
        payload = {
            "run_id": context.run_id,
            "manifest": context.manifest,
            "state": context.state,
            "active_context_id": context.active_context_id,
            "context_stack": context.context_stack,
            "retries": context.retries,
            "event_cursor": context.event_cursor,
            "artifacts": context.artifacts,
            "layered_state": asdict(context.layered_state) if is_dataclass(context.layered_state) else {},
            "last_error": context.last_error,
            "pending_transition": context.pending_transition,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
