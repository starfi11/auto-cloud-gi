from __future__ import annotations

import json
import re
from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path

from src.adapters.remote.context import RemoteContext
from src.adapters.remote.router import (
    BytesResponse,
    FileResponse,
    JsonResponse,
    Request,
    Router,
)
from src.domain.run_request import RunRequest

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


def register(router: Router, context: RemoteContext) -> None:
    orch = context.orchestrator
    logs = orch.logs
    runtime_dir = context.runtime_dir

    def _parse_body(req: Request, path: str) -> tuple[dict, JsonResponse | None]:
        if not req.body:
            return {}, None
        try:
            payload = json.loads(req.body.decode("utf-8"))
        except json.JSONDecodeError:
            logs.control_api_event(
                "request_invalid_json",
                {"method": req.method, "path": path},
                level="WARN",
            )
            return {}, JsonResponse(status=HTTPStatus.BAD_REQUEST, payload={"ok": False, "error": "invalid_json"})
        if not isinstance(payload, dict):
            return {}, JsonResponse(status=HTTPStatus.BAD_REQUEST, payload={"ok": False, "error": "invalid_json"})
        return payload, None

    def start_run(req: Request) -> JsonResponse:
        dry_run = req.path.endswith("/dry-run")
        payload, err = _parse_body(req, req.path)
        if err is not None:
            return err
        logs.control_api_event(
            "request_received",
            {"method": "POST", "path": req.path, "content_length": len(req.body)},
        )
        trigger = str(payload.get("trigger", "API_TRIGGER"))
        target_profile = str(payload.get("target_profile", "genshin_cloud_bettergi"))
        scenario = str(payload.get("scenario", "daily_default"))
        idempotency_key = str(payload.get("idempotency_key", ""))
        requested_policy_override = payload.get("requested_policy_override", {})
        if not idempotency_key:
            logs.control_api_event(
                "request_missing_idempotency_key",
                {"path": req.path, "trigger": trigger, "target_profile": target_profile, "scenario": scenario},
                level="WARN",
            )
            return JsonResponse(status=HTTPStatus.BAD_REQUEST, payload={"ok": False, "error": "missing_idempotency_key"})
        if not isinstance(requested_policy_override, dict):
            logs.control_api_event(
                "request_invalid_override",
                {"path": req.path, "trigger": trigger, "target_profile": target_profile, "scenario": scenario},
                level="WARN",
            )
            return JsonResponse(status=HTTPStatus.BAD_REQUEST, payload={"ok": False, "error": "invalid_override"})

        if dry_run:
            logs.control_api_event(
                "request_dry_run_validated",
                {
                    "trigger": trigger,
                    "target_profile": target_profile,
                    "scenario": scenario,
                    "idempotency_key": idempotency_key,
                },
            )
            return JsonResponse(
                payload={
                    "ok": True,
                    "dry_run": True,
                    "validated": {
                        "trigger": trigger,
                        "target_profile": target_profile,
                        "scenario": scenario,
                        "idempotency_key": idempotency_key,
                        "requested_policy_override": requested_policy_override,
                    },
                }
            )

        try:
            receipt = orch.start_run(
                RunRequest(
                    trigger=trigger,
                    idempotency_key=idempotency_key,
                    target_profile=target_profile,
                    scenario=scenario,
                    requested_policy_override=requested_policy_override,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logs.control_api_event(
                "request_run_failed",
                {
                    "trigger": trigger,
                    "target_profile": target_profile,
                    "scenario": scenario,
                    "error": str(exc),
                },
                level="ERROR",
            )
            return JsonResponse(status=HTTPStatus.INTERNAL_SERVER_ERROR, payload={"ok": False, "error": "run_start_failed"})

        code = HTTPStatus.ACCEPTED if receipt.accepted else HTTPStatus.CONFLICT
        logs.control_api_event(
            "request_run_submitted",
            {
                "accepted": receipt.accepted,
                "run_id": receipt.run_id,
                "reason": receipt.reason,
                "target_profile": target_profile,
                "scenario": scenario,
            },
        )
        return JsonResponse(status=code, payload={"ok": receipt.accepted, "receipt": asdict(receipt)})

    def signal_run(req: Request) -> JsonResponse:
        run_id = req.params["id"]
        kind = req.params["signal"]
        payload, err = _parse_body(req, req.path)
        if err is not None:
            return err
        reason = str(payload.get("reason", "")) if isinstance(payload, dict) else ""
        if kind == "interrupt":
            ok = orch.interrupt_run(run_id, reason or "manual_interrupt")
            label = "interrupt"
        elif kind == "risk":
            ok = orch.risk_stop_run(run_id, reason or "risk_detected")
            label = "risk_stop"
        else:
            return JsonResponse(status=HTTPStatus.NOT_FOUND, payload={"ok": False, "error": "not_found"})
        if not ok:
            return JsonResponse(
                status=HTTPStatus.NOT_FOUND,
                payload={"ok": False, "error": "run_not_found_or_not_active"},
            )
        return JsonResponse(payload={"ok": True, "run_id": run_id, "signal": label})

    def list_runs(_req: Request) -> JsonResponse:
        records = orch.list_runs()
        records_sorted = sorted(
            records,
            key=lambda r: r.created_at,
            reverse=True,
        )
        active = orch.active_run_id()
        return JsonResponse(
            payload={
                "ok": True,
                "active_run_id": active,
                "runs": [asdict(r) for r in records_sorted],
            }
        )

    def get_run(req: Request) -> JsonResponse:
        run_id = req.params["id"]
        run = orch.get_run(run_id)
        if run is None:
            logs.control_api_event("run_not_found", {"run_id": run_id}, level="WARN")
            return JsonResponse(status=HTTPStatus.NOT_FOUND, payload={"ok": False, "error": "run_not_found"})
        logs.control_api_event("run_fetched", {"run_id": run_id, "status": run.status})
        return JsonResponse(payload={"ok": True, "run": asdict(run)})

    def run_events(req: Request) -> JsonResponse:
        run_id = req.params["id"]
        if not _SAFE_SEGMENT.match(run_id):
            return JsonResponse(status=HTTPStatus.BAD_REQUEST, payload={"ok": False, "error": "invalid_run_id"})
        try:
            since = int(req.query.get("since", "0"))
        except ValueError:
            since = 0
        try:
            limit = int(req.query.get("limit", "500"))
        except ValueError:
            limit = 500
        limit = max(1, min(5000, limit))
        stream = (req.query.get("stream") or "events").strip()
        allowed = {"events", "state_transitions", "actions", "replay_trace"}
        if stream not in allowed:
            return JsonResponse(status=HTTPStatus.BAD_REQUEST, payload={"ok": False, "error": "invalid_stream"})

        events_path = runtime_dir / "logs" / "runs" / run_id / f"{stream}.jsonl"
        if not events_path.exists():
            return JsonResponse(payload={"ok": True, "run_id": run_id, "stream": stream, "events": [], "next_since": since})

        events: list[dict] = []
        next_since = since
        with events_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                seq = evt.get("seq")
                if isinstance(seq, int) and seq <= since:
                    continue
                events.append(evt)
                if isinstance(seq, int) and seq > next_since:
                    next_since = seq
                if len(events) >= limit:
                    break
        return JsonResponse(
            payload={
                "ok": True,
                "run_id": run_id,
                "stream": stream,
                "events": events,
                "next_since": next_since,
            }
        )

    def run_summary(req: Request) -> JsonResponse:
        run_id = req.params["id"]
        if not _SAFE_SEGMENT.match(run_id):
            return JsonResponse(status=HTTPStatus.BAD_REQUEST, payload={"ok": False, "error": "invalid_run_id"})
        path = runtime_dir / "logs" / "runs" / run_id / "summary.json"
        if not path.exists():
            return JsonResponse(status=HTTPStatus.NOT_FOUND, payload={"ok": False, "error": "summary_not_found"})
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return JsonResponse(status=HTTPStatus.INTERNAL_SERVER_ERROR, payload={"ok": False, "error": str(exc)})
        return JsonResponse(payload={"ok": True, "run_id": run_id, "summary": data})

    def run_diagnostics(req: Request) -> JsonResponse:
        run_id = req.params["id"]
        if not _SAFE_SEGMENT.match(run_id):
            return JsonResponse(status=HTTPStatus.BAD_REQUEST, payload={"ok": False, "error": "invalid_run_id"})
        path = runtime_dir / "logs" / "runs" / run_id / "diagnostics.json"
        if not path.exists():
            return JsonResponse(status=HTTPStatus.NOT_FOUND, payload={"ok": False, "error": "diagnostics_not_found"})
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return JsonResponse(status=HTTPStatus.INTERNAL_SERVER_ERROR, payload={"ok": False, "error": str(exc)})
        return JsonResponse(payload={"ok": True, "run_id": run_id, "diagnostics": data})

    def run_frames_list(req: Request) -> JsonResponse:
        run_id = req.params["id"]
        if not _SAFE_SEGMENT.match(run_id):
            return JsonResponse(status=HTTPStatus.BAD_REQUEST, payload={"ok": False, "error": "invalid_run_id"})
        frame_dir = runtime_dir / "logs" / "runs" / run_id / "frames"
        if not frame_dir.is_dir():
            return JsonResponse(payload={"ok": True, "run_id": run_id, "frames": []})
        names = sorted(
            p.name for p in frame_dir.iterdir() if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg"}
        )
        return JsonResponse(payload={"ok": True, "run_id": run_id, "frames": names})

    def run_frame_get(req: Request) -> FileResponse | JsonResponse:
        run_id = req.params["id"]
        name = req.params["name"]
        if not _SAFE_SEGMENT.match(run_id) or not _SAFE_SEGMENT.match(name):
            return JsonResponse(status=HTTPStatus.BAD_REQUEST, payload={"ok": False, "error": "invalid_name"})
        # Defense-in-depth: resolve and confirm containment.
        frame_dir = (runtime_dir / "logs" / "runs" / run_id / "frames").resolve()
        target = (frame_dir / name).resolve()
        try:
            target.relative_to(frame_dir)
        except ValueError:
            return JsonResponse(status=HTTPStatus.BAD_REQUEST, payload={"ok": False, "error": "path_escape"})
        if not target.exists() or not target.is_file():
            return JsonResponse(status=HTTPStatus.NOT_FOUND, payload={"ok": False, "error": "frame_not_found"})
        ext = target.suffix.lower()
        ct = "image/png" if ext == ".png" else "image/jpeg"
        return FileResponse(path=str(target), content_type=ct)

    router.register("POST", "/api/v1/runs", start_run)
    router.register("POST", "/api/v1/runs/dry-run", start_run)
    router.register("POST", "/api/v1/runs/{id}/{signal}", signal_run)
    router.register("GET", "/api/v1/runs", list_runs)
    router.register("GET", "/api/v1/runs/{id}", get_run)
    router.register("GET", "/api/v1/runs/{id}/events", run_events)
    router.register("GET", "/api/v1/runs/{id}/summary", run_summary)
    router.register("GET", "/api/v1/runs/{id}/diagnostics", run_diagnostics)
    router.register("GET", "/api/v1/runs/{id}/frames", run_frames_list)
    router.register("GET", "/api/v1/runs/{id}/frames/{name}", run_frame_get)
