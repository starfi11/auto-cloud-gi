from __future__ import annotations

from time import sleep
from typing import Any

from src.ports.assistant_runtime_port import AssistantRuntimePort


class NoopAssistantRuntimeAdapter(AssistantRuntimePort):
    def launch(self, options: dict[str, Any]) -> dict[str, Any]:
        sleep(0.01)
        return {"ok": True, "detail": "noop_assistant_launch", "options": options}

    def drive(self, scenario: str, options: dict[str, Any]) -> dict[str, Any]:
        sleep(0.01)
        return {"ok": True, "detail": "noop_assistant_drive", "scenario": scenario, "options": options}

    def collect(self, options: dict[str, Any]) -> dict[str, Any]:
        sleep(0.01)
        return {"ok": True, "detail": "noop_collect", "options": options}

    def stop(self) -> dict[str, Any]:
        return {"ok": True, "detail": "noop_assistant_stop"}
