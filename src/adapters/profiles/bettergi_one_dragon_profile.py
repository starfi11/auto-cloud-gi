from __future__ import annotations

from src.adapters.profiles.topology_segments import build_btgi_segment
from src.domain.run_request import RunRequest
from src.domain.workflow import StatePlan, WorkflowPlan
from src.ports.profile_port import AutomationProfilePort


class BetterGIOneDragonProfile(AutomationProfilePort):
    @property
    def profile_name(self) -> str:
        return "bettergi_one_dragon"

    def build_plan(self, request: RunRequest) -> WorkflowPlan:
        scenario = request.scenario or "one_dragon"
        override = request.requested_policy_override
        btgi = build_btgi_segment(override, scenario=scenario)

        state_plan = StatePlan(
            initial_state=btgi.initial_state,
            terminal_states=[btgi.done_state],
            max_ticks=int(override.get("state_max_ticks", 220)),
            nodes=btgi.nodes,
        )

        return WorkflowPlan(
            profile=self.profile_name,
            game="bettergi",
            scenario=scenario,
            mode="state_driven",
            state_plan=state_plan,
            steps=btgi.steps,
        )
