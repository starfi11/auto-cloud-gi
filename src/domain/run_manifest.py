from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    trigger: str
    target_profile: str
    scenario: str
    workflow_plan: dict[str, Any]
    effective_policy: dict[str, Any]
    created_at: str

    @staticmethod
    def build(
        run_id: str,
        trigger: str,
        target_profile: str,
        scenario: str,
        workflow_plan: dict[str, Any],
        effective_policy: dict[str, Any],
    ) -> "RunManifest":
        return RunManifest(
            run_id=run_id,
            trigger=trigger,
            target_profile=target_profile,
            scenario=scenario,
            workflow_plan=workflow_plan,
            effective_policy=effective_policy,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "trigger": self.trigger,
            "target_profile": self.target_profile,
            "scenario": self.scenario,
            "workflow_plan": self.workflow_plan,
            "effective_policy": self.effective_policy,
            "created_at": self.created_at,
        }
