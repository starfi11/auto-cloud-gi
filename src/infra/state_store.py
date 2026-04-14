from __future__ import annotations

from pathlib import Path
import json
from threading import Lock
from typing import Any


class StateStore:
    def __init__(self, runtime_dir: str) -> None:
        self._root = Path(runtime_dir) / "state"
        self._root.mkdir(parents=True, exist_ok=True)
        self._path = self._root / "orchestrator_state.json"
        self._lock = Lock()
        if not self._path.exists():
            self._write({"idempotency_map": {}, "run_records": {}})

    def _read(self) -> dict[str, Any]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return {"idempotency_map": {}, "run_records": {}}

    def _write(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
        with self._lock:
            payload = self._read()
            idem = payload.get("idempotency_map", {})
            recs = payload.get("run_records", {})
            if not isinstance(idem, dict):
                idem = {}
            if not isinstance(recs, dict):
                recs = {}
            return dict(idem), dict(recs)

    def save(self, idempotency_map: dict[str, str], run_records: dict[str, dict[str, Any]]) -> None:
        with self._lock:
            self._write({"idempotency_map": dict(idempotency_map), "run_records": dict(run_records)})
