from __future__ import annotations

from enum import StrEnum


class DomainCommand(StrEnum):
    SKIP_NEXT_RUN = "SKIP_NEXT_RUN"
    OVERRIDE_TASK_ONCE = "OVERRIDE_TASK_ONCE"
    DISABLE_FEATURE_ONCE = "DISABLE_FEATURE_ONCE"
    RESUME_DEFAULT = "RESUME_DEFAULT"
