from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from src.adapters.remote.context import RemoteContext
from src.adapters.remote.router import (
    FileResponse,
    JsonResponse,
    Request,
    Response,
    Router,
    TextResponse,
)

_MIME = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".map": "application/json; charset=utf-8",
}


def register(router: Router, context: RemoteContext) -> None:
    frontend_dir = context.frontend_dir

    def _serve(rel_path: str) -> Response:
        if frontend_dir is None:
            return JsonResponse(
                status=HTTPStatus.NOT_FOUND,
                payload={"ok": False, "error": "frontend_not_configured"},
            )
        root = frontend_dir.resolve()
        candidate = (root / rel_path.lstrip("/")).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return JsonResponse(status=HTTPStatus.BAD_REQUEST, payload={"ok": False, "error": "path_escape"})
        if candidate.is_dir():
            candidate = candidate / "index.html"
        if not candidate.exists() or not candidate.is_file():
            # SPA fallback — serve index.html so client-side routing works.
            index = root / "index.html"
            if index.exists():
                return FileResponse(path=str(index), content_type=_MIME[".html"])
            return JsonResponse(status=HTTPStatus.NOT_FOUND, payload={"ok": False, "error": "not_found"})
        ct = _MIME.get(candidate.suffix.lower(), "application/octet-stream")
        return FileResponse(path=str(candidate), content_type=ct)

    def index(_req: Request) -> Response:
        if frontend_dir is None:
            return TextResponse(
                text=(
                    "auto-cloud-gi control API.\n"
                    "No frontend bundle configured (CONTROL_API_FRONTEND_DIR unset).\n"
                    "See /api/v1/health for service status.\n"
                ),
            )
        return _serve("index.html")

    def asset(req: Request) -> Response:
        return _serve(req.params["path"])

    router.register("GET", "/", index)
    router.register("GET", "/assets/{*path}", asset)
