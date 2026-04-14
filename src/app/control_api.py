from __future__ import annotations

from dataclasses import asdict
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from src.domain.run_request import RunRequest
from src.app.orchestrator import Orchestrator


class ControlApiHandler(BaseHTTPRequestHandler):
    orchestrator: Orchestrator

    def log_message(self, format: str, *args: Any) -> None:
        # Redirect default http.server access log into structured control-api log.
        self.orchestrator.logs.control_api_event(
            "http_access",
            {"client": self.client_address[0], "message": format % args},
        )

    def _json_response(self, code: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        segments = [seg for seg in path.split("/") if seg]
        if len(segments) == 5 and segments[:3] == ["api", "v1", "runs"] and segments[4] in {"interrupt", "risk"}:
            run_id = segments[3]
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length > 0 else b"{}"
            reason = ""
            if body:
                try:
                    payload = json.loads(body.decode("utf-8"))
                    if isinstance(payload, dict):
                        reason = str(payload.get("reason", ""))
                except json.JSONDecodeError:
                    self.orchestrator.logs.control_api_event(
                        "request_invalid_json",
                        {"method": "POST", "path": path},
                        level="WARN",
                    )
                    self._json_response(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_json"})
                    return

            if segments[4] == "interrupt":
                ok = self.orchestrator.interrupt_run(run_id, reason or "manual_interrupt")
                if not ok:
                    self._json_response(HTTPStatus.NOT_FOUND, {"ok": False, "error": "run_not_found_or_not_active"})
                    return
                self._json_response(HTTPStatus.OK, {"ok": True, "run_id": run_id, "signal": "interrupt"})
                return

            ok = self.orchestrator.risk_stop_run(run_id, reason or "risk_detected")
            if not ok:
                self._json_response(HTTPStatus.NOT_FOUND, {"ok": False, "error": "run_not_found_or_not_active"})
                return
            self._json_response(HTTPStatus.OK, {"ok": True, "run_id": run_id, "signal": "risk_stop"})
            return

        if path not in {"/api/v1/runs", "/api/v1/runs/dry-run"}:
            self.orchestrator.logs.control_api_event(
                "request_not_found",
                {"method": "POST", "path": path},
                level="WARN",
            )
            self._json_response(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b"{}"
        self.orchestrator.logs.control_api_event(
            "request_received",
            {"method": "POST", "path": path, "content_length": length},
        )
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self.orchestrator.logs.control_api_event(
                "request_invalid_json",
                {"method": "POST", "path": path},
                level="WARN",
            )
            self._json_response(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_json"})
            return

        trigger = str(payload.get("trigger", "API_TRIGGER"))
        target_profile = str(payload.get("target_profile", "genshin_cloud_bettergi"))
        scenario = str(payload.get("scenario", "daily_default"))
        idempotency_key = str(payload.get("idempotency_key", ""))
        if not idempotency_key:
            self.orchestrator.logs.control_api_event(
                "request_missing_idempotency_key",
                {"path": path, "trigger": trigger, "target_profile": target_profile, "scenario": scenario},
                level="WARN",
            )
            self._json_response(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "missing_idempotency_key"})
            return

        requested_policy_override = payload.get("requested_policy_override", {})
        if not isinstance(requested_policy_override, dict):
            self.orchestrator.logs.control_api_event(
                "request_invalid_override",
                {"path": path, "trigger": trigger, "target_profile": target_profile, "scenario": scenario},
                level="WARN",
            )
            self._json_response(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_override"})
            return

        if path.endswith("/dry-run"):
            self.orchestrator.logs.control_api_event(
                "request_dry_run_validated",
                {
                    "trigger": trigger,
                    "target_profile": target_profile,
                    "scenario": scenario,
                    "idempotency_key": idempotency_key,
                },
            )
            self._json_response(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "dry_run": True,
                    "validated": {
                        "trigger": trigger,
                        "target_profile": target_profile,
                        "scenario": scenario,
                        "idempotency_key": idempotency_key,
                        "requested_policy_override": requested_policy_override,
                    },
                },
            )
            return

        try:
            receipt = self.orchestrator.start_run(
                RunRequest(
                    trigger=trigger,
                    idempotency_key=idempotency_key,
                    target_profile=target_profile,
                    scenario=scenario,
                    requested_policy_override=requested_policy_override,
                )
            )
        except Exception as exc:
            self.orchestrator.logs.control_api_event(
                "request_run_failed",
                {
                    "trigger": trigger,
                    "target_profile": target_profile,
                    "scenario": scenario,
                    "error": str(exc),
                },
                level="ERROR",
            )
            self._json_response(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "run_start_failed"})
            return
        code = HTTPStatus.ACCEPTED if receipt.accepted else HTTPStatus.CONFLICT
        self.orchestrator.logs.control_api_event(
            "request_run_submitted",
            {
                "accepted": receipt.accepted,
                "run_id": receipt.run_id,
                "reason": receipt.reason,
                "target_profile": target_profile,
                "scenario": scenario,
            },
        )
        self._json_response(code, {"ok": receipt.accepted, "receipt": asdict(receipt)})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/v1/runs/"):
            self.orchestrator.logs.control_api_event(
                "request_not_found",
                {"method": "GET", "path": parsed.path},
                level="WARN",
            )
            self._json_response(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return
        run_id = parsed.path.rsplit("/", 1)[-1]
        run = self.orchestrator.get_run(run_id)
        if run is None:
            self.orchestrator.logs.control_api_event(
                "run_not_found",
                {"run_id": run_id},
                level="WARN",
            )
            self._json_response(HTTPStatus.NOT_FOUND, {"ok": False, "error": "run_not_found"})
            return
        self.orchestrator.logs.control_api_event("run_fetched", {"run_id": run_id, "status": run.status})
        self._json_response(HTTPStatus.OK, {"ok": True, "run": asdict(run)})


def run_control_api(host: str, port: int, orchestrator: Orchestrator) -> None:
    handler_cls = ControlApiHandler
    handler_cls.orchestrator = orchestrator
    server = ThreadingHTTPServer((host, port), handler_cls)
    orchestrator.logs.control_api_event("server_started", {"host": host, "port": port})
    print(f"[control-api] listening on http://{host}:{port}")
    server.serve_forever()
