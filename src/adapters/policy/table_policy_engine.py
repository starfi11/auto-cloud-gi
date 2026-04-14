from __future__ import annotations

from src.domain.state_kernel import PolicyDecision, StateEstimate
from src.domain.workflow import WorkflowPlan
from src.kernel.context_store import RunContext
from src.ports.policy_engine_port import PolicyEnginePort


class TablePolicyEngine(PolicyEnginePort):
    def decide(self, context: RunContext, plan: WorkflowPlan, estimate: StateEstimate) -> PolicyDecision:
        state_plan = plan.state_plan
        if state_plan is None:
            return PolicyDecision(kind="fail", error="missing_state_plan", reason="state_plan_required")

        observed_state = estimate.state
        current_state = context.state or state_plan.initial_state
        if current_state in state_plan.terminal_states:
            return PolicyDecision(kind="finish", reason="terminal_state_reached")

        current_node = state_plan.node_for(current_state)
        if current_node is None:
            return PolicyDecision(
                kind="fail",
                error=f"unknown_state:{current_state}",
                reason="state_not_in_plan",
            )

        # Recognizer-driven transition is allowed only in observation states (no bound action).
        # Action states must execute their action first, otherwise we may skip critical side effects.
        can_sync_by_observation = current_node.action is None
        observation_sync_threshold = 0.75
        if can_sync_by_observation and observed_state != current_state and observed_state:
            observed_node = state_plan.node_for(observed_state)
            if observed_state in state_plan.terminal_states and estimate.confidence >= observation_sync_threshold:
                return PolicyDecision(kind="finish", reason="terminal_state_observed")
            if observed_node is not None and estimate.confidence >= observation_sync_threshold:
                # Prevent infinite re-entry to an action state that already executed.
                # If we just came from that state (its action ran and brought us here),
                # require a cooldown before syncing back to it.
                reentry_key = f"_action_done:{observed_state}"
                reentry_count = int(context.retries.get(reentry_key, 0))
                max_reentries = self._max_state_reentries(context)
                if observed_node.action is not None and reentry_count > 0:
                    if reentry_count >= max_reentries:
                        return PolicyDecision(
                            kind="fail",
                            error=f"state_reentry_limit:{observed_state}:count={reentry_count}",
                            reason="state_reentry_limit_exceeded",
                            controller_id=observed_node.controller_id,
                            context_id=observed_node.context_id,
                        )
                    # Require extra settling ticks proportional to reentry count
                    # to give the screen more time to change after a click.
                    extra_settle = reentry_count * max(2, int(observed_node.stable_ticks))
                    seen_key = f"_observed_seen:{observed_state}"
                    seen = int(context.retries.get(seen_key, 0)) + 1
                    context.retries[seen_key] = seen
                    required_seen = max(1, int(observed_node.stable_ticks)) + extra_settle
                    if seen < required_seen:
                        return PolicyDecision(
                            kind="wait",
                            reason=f"observed_state_reentry_settling:{seen}/{required_seen}:reentry={reentry_count}",
                            wait_seconds=max(0.1, observed_node.wait_seconds),
                            controller_id=observed_node.controller_id,
                            context_id=observed_node.context_id,
                        )

                seen_key = f"_observed_seen:{observed_state}"
                seen = int(context.retries.get(seen_key, 0)) + 1
                context.retries[seen_key] = seen
                required_seen = max(1, int(observed_node.stable_ticks))
                if seen < required_seen:
                    return PolicyDecision(
                        kind="wait",
                        reason=f"observed_state_settling:{seen}/{required_seen}",
                        wait_seconds=max(0.05, observed_node.wait_seconds),
                        controller_id=observed_node.controller_id,
                        context_id=observed_node.context_id,
                    )
                return PolicyDecision(
                    kind="transition",
                    next_state=observed_state,
                    controller_id=observed_node.controller_id,
                    context_id=observed_node.context_id,
                    reason="observed_state_sync",
                )

        node = current_node

        stable_key = f"_state_seen:{current_state}"
        seen = int(context.retries.get(stable_key, 0)) + 1
        context.retries[stable_key] = seen
        required_seen = max(1, int(node.stable_ticks))
        if seen < required_seen:
            return PolicyDecision(
                kind="wait",
                reason=f"state_settling:{seen}/{required_seen}",
                wait_seconds=max(0.1, node.wait_seconds),
                controller_id=node.controller_id,
                context_id=node.context_id,
            )

        if estimate.confidence < 0.4:
            low_conf_key = f"_state_low_conf:{current_state}"
            low_conf_ticks = int(context.retries.get(low_conf_key, 0)) + 1
            context.retries[low_conf_key] = low_conf_ticks
            waited_seconds = low_conf_ticks * max(0.1, node.wait_seconds)
            if node.action is None:
                stuck_timeout_seconds = self._state_stuck_timeout_seconds(context)
                if waited_seconds >= stuck_timeout_seconds:
                    return PolicyDecision(
                        kind="fail",
                        error=f"state_stuck_no_signal:{current_state}:waited={round(waited_seconds, 1)}s",
                        reason="state_stuck_no_signal",
                        controller_id=node.controller_id,
                        context_id=node.context_id,
                    )
            else:
                # Action-bearing states: after waiting long enough, force-execute
                # the action even under low confidence. This prevents indefinite
                # hangs on states like S_BOOTSTRAP that have no recognition rules.
                force_timeout = self._action_force_timeout_seconds(context)
                if waited_seconds >= force_timeout:
                    context.retries.pop(low_conf_key, None)
                    return PolicyDecision(
                        kind="action",
                        action=node.action,
                        next_state=node.next_state,
                        controller_id=node.action.controller_id or node.controller_id,
                        context_id=node.action.required_context or node.context_id,
                        reason=f"force_execute_low_confidence:waited={round(waited_seconds, 1)}s",
                    )
            return PolicyDecision(
                kind="wait",
                reason=f"low_confidence:{round(estimate.confidence, 3)}",
                wait_seconds=max(0.1, node.wait_seconds),
                controller_id=node.controller_id,
                context_id=node.context_id,
            )
        context.retries.pop(f"_state_low_conf:{current_state}", None)

        if node.action is not None:
            return PolicyDecision(
                kind="action",
                action=node.action,
                next_state=node.next_state,
                controller_id=node.action.controller_id or node.controller_id,
                context_id=node.action.required_context or node.context_id,
                reason="execute_state_action",
            )

        if node.next_state:
            return PolicyDecision(
                kind="transition",
                next_state=node.next_state,
                controller_id=node.controller_id,
                context_id=node.context_id,
                reason="state_transition_without_action",
            )

        return PolicyDecision(
            kind="wait",
            wait_seconds=node.wait_seconds,
            controller_id=node.controller_id,
            context_id=node.context_id,
            reason="state_wait",
        )

    def _state_stuck_timeout_seconds(self, context: RunContext) -> float:
        default_seconds = 25.0
        manifest = context.manifest if isinstance(context.manifest, dict) else {}
        effective_policy = manifest.get("effective_policy", {})
        if not isinstance(effective_policy, dict):
            return default_seconds
        raw = effective_policy.get("state_stuck_timeout_seconds", default_seconds)
        try:
            return max(5.0, float(raw))
        except Exception:
            return default_seconds

    def _action_force_timeout_seconds(self, context: RunContext) -> float:
        """Timeout before force-executing an action despite low confidence."""
        default_seconds = 8.0
        manifest = context.manifest if isinstance(context.manifest, dict) else {}
        effective_policy = manifest.get("effective_policy", {})
        if not isinstance(effective_policy, dict):
            return default_seconds
        raw = effective_policy.get("action_force_timeout_seconds", default_seconds)
        try:
            return max(2.0, float(raw))
        except Exception:
            return default_seconds

    def _max_state_reentries(self, context: RunContext) -> int:
        """Max times an action state can be re-entered via observation sync."""
        default = 3
        manifest = context.manifest if isinstance(context.manifest, dict) else {}
        effective_policy = manifest.get("effective_policy", {})
        if not isinstance(effective_policy, dict):
            return default
        raw = effective_policy.get("max_state_reentries", default)
        try:
            return max(1, int(raw))
        except Exception:
            return default
