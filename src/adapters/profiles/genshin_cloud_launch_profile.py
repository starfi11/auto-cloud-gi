from __future__ import annotations

from src.adapters.profiles.topology_segments import build_cloud_segment
from src.domain.run_request import RunRequest
from src.domain.workflow import StatePlan, WorkflowPlan
from src.ports.profile_port import AutomationProfilePort


class GenshinCloudLaunchProfile(AutomationProfilePort):
    @property
    def profile_name(self) -> str:
        return "genshin_cloud_launch"

    def build_plan(self, request: RunRequest) -> WorkflowPlan:
        scenario = request.scenario or "cloud_launch"
        override = request.requested_policy_override
        cloud = build_cloud_segment(override)

        state_plan = StatePlan(
            initial_state=cloud.initial_state,
            terminal_states=[cloud.done_state],
            max_ticks=int(override.get("state_max_ticks", 320)),
            nodes=cloud.nodes,
        )

        return WorkflowPlan(
            profile=self.profile_name,
            game="genshin_cloud",
            scenario=scenario,
            mode="state_driven",
            state_plan=state_plan,
            steps=cloud.steps,
        )
