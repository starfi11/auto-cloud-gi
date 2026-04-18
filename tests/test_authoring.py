from __future__ import annotations

import unittest

from src.domain.authoring import Phase, PhasedStateNode
from src.domain.blackboard import Blackboard, Guard
from src.domain.workflow import ActionIntent, StatePlan


class PhasedStateNodeTest(unittest.TestCase):
    def _phased(self) -> PhasedStateNode:
        return PhasedStateNode(
            state="S_MENU",
            phases=[
                Phase(
                    guard=Guard("current_goal", "eq", "daily"),
                    action=ActionIntent(name="click_daily", kind="ui.click"),
                    next_state="S_DAILY",
                ),
                Phase(
                    guard=Guard("current_goal", "eq", "shop"),
                    action=ActionIntent(name="click_shop", kind="ui.click"),
                    next_state="S_SHOP",
                ),
            ],
            fallback=ActionIntent(name="close", kind="ui.close"),
            fallback_next_state="S_DONE",
            recoverability="safe_reentry",
        )

    def test_expand_emits_one_node_per_phase_plus_fallback(self) -> None:
        nodes = self._phased().expand()
        self.assertEqual(len(nodes), 3)
        self.assertEqual(nodes[0].action.name, "click_daily")
        self.assertEqual(nodes[0].guard.value, "daily")
        self.assertEqual(nodes[1].guard.value, "shop")
        self.assertIsNone(nodes[2].guard)
        self.assertEqual(nodes[2].action.name, "close")

    def test_expanded_nodes_work_with_node_for(self) -> None:
        nodes = self._phased().expand()
        plan = StatePlan(
            initial_state="S_MENU",
            terminal_states=["S_DONE"],
            nodes=nodes,
        )
        bb = Blackboard({"current_goal": "shop"})
        node = plan.node_for("S_MENU", bb)
        self.assertIsNotNone(node)
        self.assertEqual(node.action.name, "click_shop")

        bb.set("current_goal", "nobody")
        node = plan.node_for("S_MENU", bb)
        self.assertEqual(node.action.name, "close")

    def test_recoverability_propagates(self) -> None:
        nodes = self._phased().expand()
        for n in nodes:
            self.assertEqual(n.recoverability, "safe_reentry")

    def test_no_fallback_means_phases_only(self) -> None:
        phased = PhasedStateNode(
            state="S",
            phases=[
                Phase(
                    guard=Guard("x", "truthy"),
                    action=ActionIntent(name="a", kind="ui.click"),
                )
            ],
        )
        nodes = phased.expand()
        self.assertEqual(len(nodes), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
