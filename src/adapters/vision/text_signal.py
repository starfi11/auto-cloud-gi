from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import monotonic, sleep
from typing import Protocol


class TextSignalSource(Protocol):
    def read_text(self) -> str:
        ...


@dataclass
class FileTextSignalSource:
    path: str

    def read_text(self) -> str:
        p = Path(self.path)
        if not p.exists() or not p.is_file():
            return ""
        try:
            return p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""


@dataclass(frozen=True)
class TextWaitSpec:
    ready_any: list[str]
    block_any: list[str]
    timeout_seconds: float
    poll_seconds: float = 0.3


@dataclass(frozen=True)
class TextWaitResult:
    ok: bool
    detail: str
    elapsed_seconds: float
    matched_ready: str = ""
    matched_block: str = ""


class TextSignalWaiter:
    def wait_until_ready(self, source: TextSignalSource, spec: TextWaitSpec) -> TextWaitResult:
        t0 = monotonic()
        ready_terms = [s for s in spec.ready_any if str(s).strip()]
        block_terms = [s for s in spec.block_any if str(s).strip()]

        while True:
            text = source.read_text()
            for term in block_terms:
                if term in text:
                    return TextWaitResult(
                        ok=False,
                        detail="blocked_text_detected",
                        elapsed_seconds=round(monotonic() - t0, 3),
                        matched_block=term,
                    )
            for term in ready_terms:
                if term in text:
                    return TextWaitResult(
                        ok=True,
                        detail="ready_text_detected",
                        elapsed_seconds=round(monotonic() - t0, 3),
                        matched_ready=term,
                    )

            elapsed = monotonic() - t0
            if elapsed >= spec.timeout_seconds:
                return TextWaitResult(
                    ok=False,
                    detail="ready_text_timeout",
                    elapsed_seconds=round(elapsed, 3),
                )
            sleep(max(0.05, spec.poll_seconds))
