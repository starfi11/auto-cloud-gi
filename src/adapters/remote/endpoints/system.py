from __future__ import annotations

from src.adapters.remote.context import RemoteContext
from src.adapters.remote.router import JsonResponse, Request, Router


def register(router: Router, context: RemoteContext) -> None:
    def health(_req: Request) -> JsonResponse:
        active = context.orchestrator.active_run_id()
        return JsonResponse(
            payload={
                "ok": True,
                "auth_enabled": context.auth.enabled,
                "active_run_id": active,
                "runtime_dir": str(context.runtime_dir),
                "frontend_dir": str(context.frontend_dir) if context.frontend_dir else None,
            }
        )

    router.register("GET", "/api/v1/health", health)
