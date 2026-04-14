from __future__ import annotations

from typing import Any, Protocol


class OcrEnginePort(Protocol):
    def read_text(self, image: Any) -> str:
        ...
