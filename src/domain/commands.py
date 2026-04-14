from __future__ import annotations

try:
    from enum import StrEnum
except ImportError:  # Python 3.10 compatibility
    from enum import Enum

    class StrEnum(str, Enum):
        pass


class DomainCommand(StrEnum):
    SKIP_NEXT_RUN = "SKIP_NEXT_RUN"
    OVERRIDE_TASK_ONCE = "OVERRIDE_TASK_ONCE"
    DISABLE_FEATURE_ONCE = "DISABLE_FEATURE_ONCE"
    RESUME_DEFAULT = "RESUME_DEFAULT"
