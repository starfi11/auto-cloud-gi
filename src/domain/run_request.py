from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RunRequest:
    trigger: str
    idempotency_key: str
    target_profile: str = "genshin_cloud_bettergi"
    scenario: str = "daily_default"
    requested_policy_override: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunReceipt:
    run_id: str
    accepted: bool
    reason: str = ""
