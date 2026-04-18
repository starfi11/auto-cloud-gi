import unittest

from src.adapters.policy import TablePolicyEngine
from src.domain.blackboard import Guard
from src.domain.state_kernel import StateEstimate
from src.domain.workflow import ActionIntent, StateNode, StatePlan, WorkflowPlan
from src.kernel.context_store import RunContext


class TablePolicyEngineTest(unittest.TestCase):
    def test_low_confidence_returns_wait(self) -> None:
        engine = TablePolicyEngine()
        plan = WorkflowPlan(
            profile="p",
            game="g",
            scenario="s",
            mode="state_driven",
            state_plan=StatePlan(
                initial_state="S1",
                terminal_states=["DONE"],
                nodes=[
                    StateNode(
                        state="S1",
                        wait_seconds=0.3,
                        action=ActionIntent(name="a", kind="game.launch"),
                    )
                ],
            ),
        )
        ctx = RunContext(run_id="r", manifest={}, state="S1")
        decision = engine.decide(ctx, plan, StateEstimate(state="S1", confidence=0.2))
        self.assertEqual(decision.kind, "wait")
        self.assertIn("low_confidence", decision.reason)

    def test_guard_selects_phase_action(self) -> None:
        # Two nodes share state S_MENU; policy should pick the one whose
        # guard matches the current blackboard goal.
        engine = TablePolicyEngine()
        plan = WorkflowPlan(
            profile="p",
            game="g",
            scenario="s",
            mode="state_driven",
            state_plan=StatePlan(
                initial_state="S_MENU",
                terminal_states=["DONE"],
                nodes=[
                    StateNode(
                        state="S_MENU",
                        action=ActionIntent(name="click_daily", kind="ui.click"),
                        next_state="DONE",
                        stable_ticks=1,
                        guard=Guard("current_goal", "eq", "daily"),
                    ),
                    StateNode(
                        state="S_MENU",
                        action=ActionIntent(name="click_shop", kind="ui.click"),
                        next_state="DONE",
                        stable_ticks=1,
                        guard=Guard("current_goal", "eq", "shop"),
                    ),
                ],
            ),
        )
        ctx = RunContext(run_id="r", manifest={}, state="S_MENU")
        ctx.blackboard.set("current_goal", "shop")
        # Bump stable_ticks counter so we skip settling.
        ctx.retries["_state_seen:S_MENU"] = 1
        decision = engine.decide(ctx, plan, StateEstimate(state="S_MENU", confidence=1.0))
        self.assertEqual(decision.kind, "action")
        self.assertEqual(decision.action.name, "click_shop")


if __name__ == "__main__":
    unittest.main()
