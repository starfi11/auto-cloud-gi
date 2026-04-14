from __future__ import annotations

from src.ports.scheduler_port import SchedulerPort


class ECSApiAdapter(SchedulerPort):
    def start_instance(self, instance_id: str) -> bool:
        # TODO: direct ECS API adapter implementation
        return True

    def stop_instance(self, instance_id: str) -> bool:
        # TODO: direct ECS API adapter implementation
        return True
