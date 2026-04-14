#!/usr/bin/env python3
"""Manual smoke runner for local control API.

Usage examples:
  python scripts/smoke_run.py --wait
  python scripts/smoke_run.py --profile genshin_pc_bettergi --wait
  python scripts/smoke_run.py --run-id <existing_run_id>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


FINAL_STATES = {"finished", "failed", "interrupted", "risk_stopped"}


def _http_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url=url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc


def create_run(args: argparse.Namespace) -> str:
    idem = args.idempotency_key or f"smoke-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    payload = {
        "trigger": "API_TRIGGER",
        "idempotency_key": idem,
        "target_profile": args.profile,
        "scenario": args.scenario,
        "requested_policy_override": {
            "assistant_log_root": args.assistant_log_root,
            "assistant_log_glob": args.assistant_log_glob,
            "assistant_idle_seconds": args.assistant_idle_seconds,
            "assistant_timeout_seconds": args.assistant_timeout_seconds,
            "assistant_require_log_activity": args.assistant_require_log_activity,
            "use_text_signal_wait": args.use_text_signal_wait,
            "queue_strategy": args.queue_strategy,
        },
    }
    url = f"{args.api_base.rstrip('/')}/api/v1/runs"
    resp = _http_json("POST", url, payload)
    if not resp.get("ok"):
        raise RuntimeError(f"run not accepted: {resp}")
    run_id = resp.get("receipt", {}).get("run_id")
    if not run_id:
        raise RuntimeError(f"run_id missing: {resp}")
    print(f"RUN_ID={run_id}")
    return run_id


def watch_run(args: argparse.Namespace, run_id: str) -> int:
    url = f"{args.api_base.rstrip('/')}/api/v1/runs/{run_id}"
    while True:
        resp = _http_json("GET", url)
        run = resp.get("run", {})
        status = run.get("status", "unknown")
        reason = run.get("reason", "")
        print(f"status={status} reason={reason}")
        if status in FINAL_STATES:
            break
        time.sleep(max(1, args.poll_seconds))

    run_dir = Path(args.runtime_dir) / "logs" / "runs" / run_id
    diag = run_dir / "diagnostics.json"
    summary = run_dir / "summary.json"
    if diag.exists():
        print("=== diagnostics.json ===")
        print(diag.read_text(encoding="utf-8", errors="replace"))
    if summary.exists():
        print("=== summary.json ===")
        print(summary.read_text(encoding="utf-8", errors="replace"))
    return 0 if status == "finished" else 1


def main() -> int:
    p = argparse.ArgumentParser(description="Create/watch a local automation run")
    p.add_argument("--api-base", default="http://127.0.0.1:8788")
    p.add_argument("--runtime-dir", default="./runtime")
    p.add_argument("--profile", default="genshin_cloud_bettergi")
    p.add_argument("--scenario", default="daily_default")
    p.add_argument("--idempotency-key", default="")
    p.add_argument("--run-id", default="", help="watch existing run only")
    p.add_argument("--wait", action="store_true", help="wait until run reaches final state")
    p.add_argument("--poll-seconds", type=int, default=2)

    p.add_argument("--assistant-log-root", default="C:/Program Files/BetterGI/log")
    p.add_argument("--assistant-log-glob", default="better-genshin-impact*.log")
    p.add_argument("--assistant-idle-seconds", type=int, default=10)
    p.add_argument("--assistant-timeout-seconds", type=int, default=180)
    p.add_argument("--assistant-require-log-activity", action="store_true")
    p.add_argument("--use-text-signal-wait", action="store_true")
    p.add_argument("--queue-strategy", default="normal", choices=["normal", "quick", "none"])

    args = p.parse_args()

    try:
        run_id = args.run_id or create_run(args)
        if args.wait or args.run_id:
            return watch_run(args, run_id)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
