from __future__ import annotations

from dataclasses import dataclass

from src.domain.run_request import RunRequest
from src.domain.workflow import WorkflowPlan
from src.ports.profile_port import AutomationProfilePort


class UnknownProfileError(ValueError):
    pass


@dataclass
class ProfileRegistry:
    _profiles: dict[str, AutomationProfilePort]
    _default_profile: str

    def resolve(self, profile_name: str | None) -> AutomationProfilePort:
        name = profile_name or self._default_profile
        profile = self._profiles.get(name)
        if profile is None:
            raise UnknownProfileError(f"unknown profile: {name}")
        return profile

    def build_plan(self, request: RunRequest) -> WorkflowPlan:
        return self.resolve(request.target_profile).build_plan(request)


