from __future__ import annotations

from dataclasses import dataclass

from src.kernel.context_store import RunContext


@dataclass(frozen=True)
class ContextSwitchResult:
    ok: bool
    source_context: str
    target_context: str
    reason: str


class ContextManager:
    def __init__(self, default_context_id: str = "global") -> None:
        self._default_context_id = default_context_id

    def current(self, context: RunContext) -> str:
        return context.active_context_id or self._default_context_id

    def ensure_initialized(self, context: RunContext) -> None:
        if not context.active_context_id:
            context.active_context_id = self._default_context_id
        if not context.context_stack:
            context.context_stack = [context.active_context_id]
        context.layered_state.context_layer.active_context_id = context.active_context_id

    def switch_to(self, context: RunContext, target_context_id: str, reason: str) -> ContextSwitchResult:
        self.ensure_initialized(context)
        source = context.active_context_id
        target = target_context_id.strip() or self._default_context_id
        if source == target:
            context.layered_state.context_layer.last_switch_reason = f"no_op:{reason}"
            return ContextSwitchResult(
                ok=True,
                source_context=source,
                target_context=target,
                reason=f"no_op:{reason}",
            )

        context.active_context_id = target
        if context.context_stack and context.context_stack[-1] == source:
            context.context_stack[-1] = target
        else:
            context.context_stack.append(target)
        context.layered_state.context_layer.active_context_id = target
        context.layered_state.context_layer.last_switch_reason = reason
        context.layered_state.context_layer.switch_count += 1

        return ContextSwitchResult(
            ok=True,
            source_context=source,
            target_context=target,
            reason=reason,
        )
