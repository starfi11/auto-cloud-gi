from __future__ import annotations

import hmac
from dataclasses import dataclass

from src.adapters.remote.router import JsonResponse, Request, Response


@dataclass(frozen=True)
class TokenAuth:
    """Header-based auth for the remote control API.

    Empty token disables auth (dev convenience) — the server surfaces this
    state via /health so operators notice. Non-empty token is matched with
    a constant-time compare to avoid leaking length via timing.
    """

    token: str
    header_name: str = "X-API-Token"
    protected_prefix: str = "/api/"

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def check(self, request: Request) -> Response | None:
        # Static assets and index must be reachable without a token so the
        # operator has somewhere to *enter* the token. Only /api/* is gated.
        if not request.path.startswith(self.protected_prefix):
            return None
        if not self.enabled:
            return None
        provided = request.header(self.header_name, "").strip()
        if not provided:
            return JsonResponse(
                status=401,
                payload={"error": "missing_token", "header": self.header_name},
            )
        if not hmac.compare_digest(provided, self.token):
            return JsonResponse(status=403, payload={"error": "invalid_token"})
        return None
