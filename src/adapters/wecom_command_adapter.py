from __future__ import annotations

from typing import Any

from src.ports.command_source_port import CommandSourcePort


class WeComCommandAdapter(CommandSourcePort):
    def fetch_effective_overrides(self) -> dict[str, Any]:
        # TODO: implement WeCom command ingestion and domain mapping
        return {}
