from __future__ import annotations

from src.ports.scheduler_port import SchedulerPort


class FCSchedulerAdapter(SchedulerPort):
    def start_instance(self, instance_id: str) -> bool:
        # TODO: implement ECS StartInstance API invocation
        return True

    def stop_instance(self, instance_id: str) -> bool:
        # TODO: implement ECS StopInstance API invocation
        return True
