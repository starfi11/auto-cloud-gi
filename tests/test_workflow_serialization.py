import unittest

from src.domain.blackboard import Guard
from src.domain.scenario import Goal, ScenarioSpec
from src.domain.workflow import ActionIntent, StateNode, StatePlan, WorkflowPlan


class WorkflowSerializationTest(unittest.TestCase):
    def test_state_plan_serialization_keeps_context_and_controller(self) -> None:
        plan = WorkflowPlan(
            profile="p",
            game="g",
            scenario="s",
            mode="state_driven",
            state_plan=StatePlan(
                initial_state="A",
                terminal_states=["DONE"],
                nodes=[
                    StateNode(
                        state="A",
                        context_id="ctx1",
                        controller_id="c1",
                        action=ActionIntent(
                            name="n",
                            kind="game.launch",
                            controller_id="c1",
                            required_context="ctx1",
                        ),
                        next_state="DONE",
                    )
                ],
            ),
        )

        payload = plan.to_dict()
        restored = WorkflowPlan.from_dict(payload)
        node = restored.state_plan.nodes[0] if restored.state_plan else None

        self.assertIsNotNone(node)
        self.assertEqual(node.context_id, "ctx1")
        self.assertEqual(node.controller_id, "c1")
        self.assertIsNotNone(node.action)
        self.assertEqual(node.action.controller_id, "c1")
        self.assertEqual(node.action.required_context, "ctx1")

    def test_scenario_spec_roundtrips(self) -> None:
        plan = WorkflowPlan(
            profile="p",
            game="g",
            scenario="daily",
            scenario_spec=ScenarioSpec(
                name="daily",
                goals=[
                    Goal("daily", until=Guard("daily_done", "truthy")),
                    Goal("shop", until=Guard("shop_done", "truthy")),
                ],
            ),
        )
        restored = WorkflowPlan.from_dict(plan.to_dict())
        self.assertIsNotNone(restored.scenario_spec)
        self.assertEqual(restored.scenario_spec.name, "daily")
        self.assertEqual([g.name for g in restored.scenario_spec.goals], ["daily", "shop"])
        self.assertEqual(restored.scenario_spec.goals[0].until.key, "daily_done")


if __name__ == "__main__":
    unittest.main()
