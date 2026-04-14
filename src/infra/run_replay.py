from __future__ import annotations

from pathlib import Path
import json
from dataclasses import dataclass


def load_run_timeline(log_root: str, run_id: str) -> list[dict[str, object]]:
    run_dir = Path(log_root) / "logs" / "runs" / run_id
    timeline: list[dict[str, object]] = []
    for rel in ("events.jsonl", "state_transitions.jsonl", "actions.jsonl"):
        p = run_dir / rel
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event.setdefault("stream", rel)
            timeline.append(event)
    return sorted(timeline, key=lambda e: int(e.get("seq", 0)))


def load_replay_trace(log_root: str, run_id: str) -> list[dict[str, object]]:
    p = Path(log_root) / "logs" / "runs" / run_id / "replay_trace.jsonl"
    if not p.exists():
        return []
    records: list[dict[str, object]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return sorted(records, key=lambda e: int(e.get("seq", 0)))


@dataclass(frozen=True)
class ReplayCheck:
    ok: bool
    replayed_final_state: str
    transition_count: int
    reason: str = ""


def replay_state_transitions(log_root: str, run_id: str) -> ReplayCheck:
    trace = load_replay_trace(log_root, run_id)
    transitions = [ev for ev in trace if ev.get("event_type") == "transition"]
    if not transitions:
        return ReplayCheck(ok=False, replayed_final_state="", transition_count=0, reason="no_transition_events")

    current = str(transitions[0].get("payload", {}).get("from", ""))
    for ev in transitions:
        payload = ev.get("payload", {})
        if not isinstance(payload, dict):
            return ReplayCheck(ok=False, replayed_final_state=current, transition_count=0, reason="bad_payload")
        source = str(payload.get("from", ""))
        target = str(payload.get("to", ""))
        if current and source and current != source:
            return ReplayCheck(
                ok=False,
                replayed_final_state=current,
                transition_count=len(transitions),
                reason=f"transition_chain_break:{current}!={source}",
            )
        current = target
    return ReplayCheck(ok=True, replayed_final_state=current, transition_count=len(transitions), reason="ok")
