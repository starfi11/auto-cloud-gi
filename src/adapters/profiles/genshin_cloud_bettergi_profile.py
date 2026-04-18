from __future__ import annotations

from src.adapters.profiles.topology_segments import build_btgi_segment, build_cloud_segment
from src.domain.run_request import RunRequest
from src.domain.workflow import StateNode, StatePlan, WorkflowPlan
from src.ports.profile_port import AutomationProfilePort


class GenshinCloudBetterGIProfile(AutomationProfilePort):
    @property
    def profile_name(self) -> str:
        return "genshin_cloud_bettergi"

    def build_plan(self, request: RunRequest) -> WorkflowPlan:
        scenario = request.scenario or "daily_default"
        override = request.requested_policy_override

        btgi = build_btgi_segment(override, scenario=scenario, done_next_state="S_DONE")
        cloud = build_cloud_segment(override, handoff_to=btgi.initial_state)

        nodes = [*cloud.nodes, *btgi.nodes, StateNode(state="S_DONE")]
        state_plan = StatePlan(
            initial_state=cloud.initial_state,
            terminal_states=["S_DONE"],
            max_ticks=int(override.get("state_max_ticks", 450)),
            nodes=nodes,
        )

        return WorkflowPlan(
            profile=self.profile_name,
            game="genshin_cloud",
            scenario=scenario,
            mode="state_driven",
            state_plan=state_plan,
            steps=[*cloud.steps, *btgi.steps],
        )
