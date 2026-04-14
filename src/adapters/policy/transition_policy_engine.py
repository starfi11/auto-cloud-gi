from __future__ import annotations

from src.adapters.policy.table_policy_engine import TablePolicyEngine


class TransitionPolicyEngine(TablePolicyEngine):
    """Policy engine for state-transition orchestration.

    Currently extends TablePolicyEngine behavior (including observed-state sync
    and settling guards) and exists as the explicit architecture entrypoint.
    """

    pass
