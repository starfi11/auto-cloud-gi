from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

from src.adapters.remote.auth import TokenAuth
from src.adapters.remote.context import RemoteContext
from src.adapters.remote.endpoints import build_router
from src.adapters.remote.router import FileResponse, JsonResponse, Request, Response, Router
from src.app.orchestrator import Orchestrator


class _Handler(BaseHTTPRequestHandler):
    # Populated by build_handler_class before binding to the server.
    router: Router
    context: RemoteContext

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        self.context.orchestrator.logs.control_api_event(
            "http_access",
            {"client": self.client_address[0], "message": format % args},
        )

    def _collect_headers(self) -> dict[str, str]:
        return {k: v for k, v in self.headers.items()}

    def _read_body(self) -> bytes:
        length_raw = self.headers.get("Content-Length", "0")
        try:
            length = int(length_raw)
        except ValueError:
            length = 0
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _dispatch(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        body = self._read_body() if self.command in {"POST", "PUT", "PATCH"} else b""

        request = Request(
            method=self.command,
            path=path,
            query=query,
            headers=self._collect_headers(),
            body=body,
        )

        auth_err = self.context.auth.check(request)
        if auth_err is not None:
            self.context.orchestrator.logs.control_api_event(
                "request_unauthorized",
                {"method": self.command, "path": path},
                level="WARN",
            )
            self._write_response(auth_err)
            return

        match = self.router.match(self.command, path)
        if match is None:
            allowed = self.router.method_allowed(path)
            if allowed:
                resp: Response = JsonResponse(
                    status=HTTPStatus.METHOD_NOT_ALLOWED,
                    headers={"Allow": ", ".join(sorted(set(allowed)))},
                    payload={"ok": False, "error": "method_not_allowed", "allowed": sorted(set(allowed))},
                )
            else:
                resp = JsonResponse(status=HTTPStatus.NOT_FOUND, payload={"ok": False, "error": "not_found"})
            self._write_response(resp)
            return

        request_with_params = Request(
            method=request.method,
            path=request.path,
            params=match.params,
            query=request.query,
            headers=request.headers,
            body=request.body,
        )
        try:
            response = match.handler(request_with_params)
        except Exception as exc:  # noqa: BLE001
            self.context.orchestrator.logs.control_api_event(
                "request_handler_error",
                {"method": self.command, "path": path, "error": str(exc), "error_type": type(exc).__name__},
                level="ERROR",
            )
            response = JsonResponse(
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                payload={"ok": False, "error": "handler_error"},
            )
        self._write_response(response)

    def _write_response(self, response: Response) -> None:
        status, headers, body_bytes, file_path = response.render()
        self.send_response(status)
        content_length: int
        if file_path is not None:
            try:
                size = Path(file_path).stat().st_size
            except OSError:
                self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "file_stat_failed")
                return
            content_length = size
        else:
            assert body_bytes is not None
            content_length = len(body_bytes)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(content_length))
        self.end_headers()
        if file_path is not None:
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(64 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        else:
            assert body_bytes is not None
            self.wfile.write(body_bytes)

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch()

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch()

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch()

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch()


def build_handler_class(router: Router, context: RemoteContext) -> type[_Handler]:
    # One handler subclass per server so multiple servers can coexist in tests
    # without sharing class-level state.
    return type(
        "ControlApiHandler",
        (_Handler,),
        {"router": router, "context": context},
    )


def run_remote_server(
    host: str,
    port: int,
    orchestrator: Orchestrator,
    *,
    token: str,
    runtime_dir: str,
    repo_dir: str = ".",
    frontend_dir: str | None = None,
) -> None:
    auth = TokenAuth(token=token)
    context = RemoteContext(
        orchestrator=orchestrator,
        auth=auth,
        runtime_dir=Path(runtime_dir),
        repo_dir=Path(repo_dir),
        frontend_dir=Path(frontend_dir) if frontend_dir else None,
    )
    router = build_router(context)
    handler_cls = build_handler_class(router, context)
    server = ThreadingHTTPServer((host, port), handler_cls)
    orchestrator.logs.control_api_event(
        "server_started",
        {
            "host": host,
            "port": port,
            "auth_enabled": auth.enabled,
            "frontend_dir": frontend_dir or None,
            "routes": [{"method": m, "template": t} for m, t in router.templates()],
        },
    )
    print(f"[control-api] listening on http://{host}:{port} auth={'on' if auth.enabled else 'off'}")
    server.serve_forever()
