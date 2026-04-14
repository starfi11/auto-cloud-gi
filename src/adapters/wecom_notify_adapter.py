from __future__ import annotations

from src.ports.notify_port import NotifyPort


class WeComNotifyAdapter(NotifyPort):
    def notify(self, title: str, body: str) -> None:
        # TODO: implement WeCom webhook delivery
        raise NotImplementedError("WeCom notify adapter is not implemented yet")
