from __future__ import annotations

from src.adapters.remote.context import RemoteContext
from src.adapters.remote.endpoints import frontend, runs, system
from src.adapters.remote.router import Router


def build_router(context: RemoteContext) -> Router:
    router = Router()
    system.register(router, context)
    runs.register(router, context)
    frontend.register(router, context)
    return router


__all__ = ["build_router"]
