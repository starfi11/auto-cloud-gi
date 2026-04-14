from __future__ import annotations

from src.ports.notify_port import NotifyPort


class StdoutNotifyAdapter(NotifyPort):
    def notify(self, title: str, body: str) -> None:
        print(f"[notify] {title}: {body}")
