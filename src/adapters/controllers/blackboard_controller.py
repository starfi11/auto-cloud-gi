from __future__ import annotations

from dataclasses import dataclass

from src.domain.workflow import WorkflowStep
from src.kernel.context_store import RunContext


_SUPPORTED_KINDS: frozenset[str] = frozenset({"bb.set", "bb.inc", "bb.delete", "bb.clear"})


@dataclass
class BlackboardController:
    """Executes bb.* macro steps against ``context.blackboard``.

    Profile authors declare state-node actions with kind="bb.inc" / "bb.set"
    to mutate run-scoped memory without touching Python. Keeps the state
    graph as the single authoring surface.
    """

    _controller_id: str = "blackboard_controller"

    @property
    def controller_id(self) -> str:
        return self._controller_id

    def supports(self, step: WorkflowStep) -> bool:
        return step.kind in _SUPPORTED_KINDS

    def execute(self, step: WorkflowStep, context: RunContext) -> dict[str, object]:
        if not self.supports(step):
            return {"ok": False, "retryable": False, "detail": f"unsupported:{step.kind}"}

        params = step.params or {}
        key = params.get("key")
        if step.kind != "bb.clear" and not isinstance(key, str):
            return {"ok": False, "retryable": False, "detail": "bb_missing_key"}

        try:
            if step.kind == "bb.set":
                context.blackboard.set(key, params.get("value"))
                return {"ok": True, "retryable": False, "detail": f"bb_set:{key}"}
            if step.kind == "bb.inc":
                delta = params.get("delta", 1)
                if not isinstance(delta, (int, float)) or isinstance(delta, bool):
                    return {"ok": False, "retryable": False, "detail": "bb_inc_bad_delta"}
                new_val = context.blackboard.inc(key, delta)
                return {"ok": True, "retryable": False, "detail": f"bb_inc:{key}={new_val}"}
            if step.kind == "bb.delete":
                context.blackboard.delete(key)
                return {"ok": True, "retryable": False, "detail": f"bb_delete:{key}"}
            if step.kind == "bb.clear":
                context.blackboard.clear()
                return {"ok": True, "retryable": False, "detail": "bb_clear"}
        except TypeError as exc:
            return {"ok": False, "retryable": False, "detail": f"bb_type_error:{exc}"}
        return {"ok": False, "retryable": False, "detail": f"unsupported:{step.kind}"}
