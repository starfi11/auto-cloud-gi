from __future__ import annotations

from typing import Protocol

from src.domain.ui_element import ElementMatchResult


class ElementResolverPort(Protocol):
    def resolve(
        self,
        *,
        element_id: str,
        profile: str = "default",
        timeout_seconds: float | None = None,
        poll_seconds: float | None = None,
    ) -> ElementMatchResult:
        ...
