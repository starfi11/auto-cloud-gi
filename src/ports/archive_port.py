from __future__ import annotations

from typing import Protocol


class ArchivePort(Protocol):
    def archive_run(self, run_id: str) -> str:
        ...
