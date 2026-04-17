#!/usr/bin/env python3
"""Remote control CLI for the auto-cloud-gi HTTP API.

Designed to be driven from a shell (human or AI): all output is JSON, all
errors exit non-zero with a human-readable stderr line. Zero non-stdlib deps.

Config via env:
  REMOTE_HOST   host[:port], default 127.0.0.1:8788 (accepts http://... too)
  REMOTE_TOKEN  X-API-Token header value. Empty = auth off on server side.
  REMOTE_TIMEOUT  float seconds, default 5.0

Usage:
  scripts/remote_ctl.py health
  scripts/remote_ctl.py runs [--status running]
  scripts/remote_ctl.py show <run_id> [--include summary,diagnostics]
  scripts/remote_ctl.py start --idem KEY [--profile P] [--scenario S] [--dry-run]
  scripts/remote_ctl.py interrupt <run_id> [--reason TXT]
  scripts/remote_ctl.py risk <run_id> [--reason TXT]
  scripts/remote_ctl.py tail <run_id> [--since N] [--stream events] [--limit 500]
                                      [--follow] [--interval 1.0]
  scripts/remote_ctl.py frames <run_id>
  scripts/remote_ctl.py frame <run_id> <name> -o PATH
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any


def _base_url() -> str:
    raw = os.getenv("REMOTE_HOST", "127.0.0.1:8788").strip()
    if not raw:
        raw = "127.0.0.1:8788"
    if not raw.startswith(("http://", "https://")):
        raw = f"http://{raw}"
    return raw.rstrip("/")


def _timeout() -> float:
    try:
        return float(os.getenv("REMOTE_TIMEOUT", "5"))
    except ValueError:
        return 5.0


def _request(
    method: str,
    path: str,
    *,
    query: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    raw_out: bool = False,
) -> tuple[int, Any, bytes]:
    """Return (status, parsed_json_or_none, raw_bytes)."""
    url = _base_url() + path
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    token = os.getenv("REMOTE_TOKEN", "").strip()
    if token:
        headers["X-API-Token"] = token
    if data is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=_timeout())
        status = resp.status
        raw = resp.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read() or b""
    except urllib.error.URLError as exc:
        print(f"error: cannot reach {url}: {exc.reason}", file=sys.stderr)
        sys.exit(2)
    if raw_out:
        return status, None, raw
    if not raw:
        return status, None, raw
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        parsed = None
    return status, parsed, raw


def _emit(status: int, payload: Any) -> int:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0 if 200 <= status < 300 else 1


def cmd_health(_args: argparse.Namespace) -> int:
    status, payload, _ = _request("GET", "/api/v1/health")
    return _emit(status, payload or {"status": status})


def cmd_runs(args: argparse.Namespace) -> int:
    status, payload, _ = _request("GET", "/api/v1/runs")
    if not args.status or not isinstance(payload, dict):
        return _emit(status, payload)
    filtered = [r for r in payload.get("runs", []) if r.get("status") == args.status]
    return _emit(status, {**payload, "runs": filtered})


def cmd_show(args: argparse.Namespace) -> int:
    status, payload, _ = _request("GET", f"/api/v1/runs/{args.run_id}")
    if status != 200 or not isinstance(payload, dict):
        return _emit(status, payload)
    out = dict(payload)
    include = {s.strip() for s in (args.include or "").split(",") if s.strip()}
    if "summary" in include:
        s, p, _ = _request("GET", f"/api/v1/runs/{args.run_id}/summary")
        out["_summary"] = p if s == 200 else {"error": p, "status": s}
    if "diagnostics" in include:
        s, p, _ = _request("GET", f"/api/v1/runs/{args.run_id}/diagnostics")
        out["_diagnostics"] = p if s == 200 else {"error": p, "status": s}
    return _emit(status, out)


def cmd_start(args: argparse.Namespace) -> int:
    path = "/api/v1/runs/dry-run" if args.dry_run else "/api/v1/runs"
    body = {
        "trigger": args.trigger,
        "target_profile": args.profile,
        "scenario": args.scenario,
        "idempotency_key": args.idem or f"cli-{uuid.uuid4()}",
    }
    status, payload, _ = _request("POST", path, body=body)
    return _emit(status, payload)


def _signal(run_id: str, signal: str, reason: str) -> int:
    status, payload, _ = _request(
        "POST", f"/api/v1/runs/{run_id}/{signal}", body={"reason": reason}
    )
    return _emit(status, payload)


def cmd_interrupt(args: argparse.Namespace) -> int:
    return _signal(args.run_id, "interrupt", args.reason)


def cmd_risk(args: argparse.Namespace) -> int:
    return _signal(args.run_id, "risk", args.reason)


def cmd_tail(args: argparse.Namespace) -> int:
    since = args.since
    if args.follow:
        # Follow mode: print each batch as a JSON line (NDJSON) so a pipe
        # can parse incrementally. Hit Ctrl-C to stop.
        try:
            while True:
                status, payload, _ = _request(
                    "GET",
                    f"/api/v1/runs/{args.run_id}/events",
                    query={"since": str(since), "stream": args.stream, "limit": str(args.limit)},
                )
                if status != 200 or not isinstance(payload, dict):
                    sys.stdout.write(json.dumps({"_error": payload, "_status": status}) + "\n")
                    sys.stdout.flush()
                    return 1
                events = payload.get("events", [])
                for evt in events:
                    sys.stdout.write(json.dumps(evt, ensure_ascii=False) + "\n")
                sys.stdout.flush()
                since = payload.get("next_since", since)
                if not events:
                    time.sleep(args.interval)
        except KeyboardInterrupt:
            return 0
    # One-shot: return whatever is newer than --since as a single JSON blob.
    status, payload, _ = _request(
        "GET",
        f"/api/v1/runs/{args.run_id}/events",
        query={"since": str(since), "stream": args.stream, "limit": str(args.limit)},
    )
    return _emit(status, payload)


def cmd_frames(args: argparse.Namespace) -> int:
    status, payload, _ = _request("GET", f"/api/v1/runs/{args.run_id}/frames")
    return _emit(status, payload)


def cmd_frame(args: argparse.Namespace) -> int:
    status, _payload, raw = _request(
        "GET", f"/api/v1/runs/{args.run_id}/frames/{args.name}", raw_out=True
    )
    if status != 200:
        try:
            print(raw.decode("utf-8"), file=sys.stderr)
        except UnicodeDecodeError:
            pass
        print(f"error: frame fetch failed status={status}", file=sys.stderr)
        return 1
    with open(args.output, "wb") as f:
        f.write(raw)
    print(json.dumps({"ok": True, "path": args.output, "bytes": len(raw)}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="remote_ctl", description="auto-cloud-gi remote control CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health").set_defaults(func=cmd_health)

    sp = sub.add_parser("runs", help="list runs")
    sp.add_argument("--status", default="", help="filter by status (optional)")
    sp.set_defaults(func=cmd_runs)

    sp = sub.add_parser("show", help="show a single run")
    sp.add_argument("run_id")
    sp.add_argument("--include", default="", help="comma-sep: summary,diagnostics")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("start", help="start a run")
    sp.add_argument("--profile", default="genshin_cloud_bettergi")
    sp.add_argument("--scenario", default="daily_default")
    sp.add_argument("--trigger", default="CLI_TRIGGER")
    sp.add_argument("--idem", default="", help="idempotency key; auto-generated if empty")
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(func=cmd_start)

    for name, fn in (("interrupt", cmd_interrupt), ("risk", cmd_risk)):
        sp = sub.add_parser(name, help=f"send {name} signal")
        sp.add_argument("run_id")
        sp.add_argument("--reason", default="cli")
        sp.set_defaults(func=fn)

    sp = sub.add_parser("tail", help="tail run events (one-shot by default)")
    sp.add_argument("run_id")
    sp.add_argument("--since", type=int, default=0)
    sp.add_argument("--stream", default="events",
                    choices=["events", "state_transitions", "actions", "replay_trace"])
    sp.add_argument("--limit", type=int, default=500)
    sp.add_argument("--follow", action="store_true",
                    help="keep polling and emit NDJSON (Ctrl-C to stop)")
    sp.add_argument("--interval", type=float, default=1.0)
    sp.set_defaults(func=cmd_tail)

    sp = sub.add_parser("frames", help="list diagnostic frames")
    sp.add_argument("run_id")
    sp.set_defaults(func=cmd_frames)

    sp = sub.add_parser("frame", help="download a frame to disk")
    sp.add_argument("run_id")
    sp.add_argument("name")
    sp.add_argument("-o", "--output", required=True)
    sp.set_defaults(func=cmd_frame)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
