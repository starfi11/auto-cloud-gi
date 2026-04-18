from __future__ import annotations

import json
import unittest

from src.domain.blackboard import (
    Blackboard,
    Guard,
    evaluate_guard,
    guard_from_dict,
    guard_to_dict,
)
from src.domain.workflow import (
    ActionIntent,
    StateNode,
    StatePlan,
    WorkflowPlan,
)


class BlackboardOpsTest(unittest.TestCase):
    def test_get_missing_returns_default(self) -> None:
        bb = Blackboard()
        self.assertIsNone(bb.get("x"))
        self.assertEqual(bb.get("x", 42), 42)
        self.assertFalse(bb.has("x"))

    def test_set_increments_version(self) -> None:
        bb = Blackboard()
        v0 = bb.version
        bb.set("phase", "daily")
        self.assertGreater(bb.version, v0)
        self.assertEqual(bb.get("phase"), "daily")

    def test_inc_on_missing_starts_at_zero(self) -> None:
        bb = Blackboard()
        self.assertEqual(bb.inc("counter"), 1)
        self.assertEqual(bb.inc("counter", 2), 3)
        self.assertEqual(bb.get("counter"), 3)

    def test_inc_rejects_non_numeric(self) -> None:
        bb = Blackboard({"name": "alice"})
        with self.assertRaises(TypeError):
            bb.inc("name")

    def test_inc_rejects_bool(self) -> None:
        # bool is technically an int in python; we don't want
        # inc("flag") silently turning True into 2.
        bb = Blackboard({"flag": True})
        with self.assertRaises(TypeError):
            bb.inc("flag")

    def test_snapshot_is_deep_copy(self) -> None:
        bb = Blackboard({"list": [1, 2, 3]})
        snap = bb.snapshot()
        snap["list"].append(99)
        self.assertEqual(bb.get("list"), [1, 2, 3])

    def test_delete_removes_key(self) -> None:
        bb = Blackboard({"x": 1})
        bb.delete("x")
        self.assertFalse(bb.has("x"))
        # Deleting missing key is a no-op (no version bump, no error).
        v = bb.version
        bb.delete("nope")
        self.assertEqual(bb.version, v)

    def test_update_batch(self) -> None:
        bb = Blackboard()
        bb.update({"a": 1, "b": 2})
        self.assertEqual(bb.get("a"), 1)
        self.assertEqual(bb.get("b"), 2)


class GuardEvaluationTest(unittest.TestCase):
    def test_none_guard_always_passes(self) -> None:
        self.assertTrue(evaluate_guard(None, None))
        self.assertTrue(evaluate_guard(None, Blackboard()))

    def test_guard_without_blackboard_fails_for_most_ops(self) -> None:
        g = Guard(key="x", op="eq", value=1)
        self.assertFalse(evaluate_guard(g, None))
        # Only "missing" passes when no blackboard and the key is treated as absent.
        self.assertTrue(evaluate_guard(Guard(key="x", op="missing"), None))

    def test_eq_ne(self) -> None:
        bb = Blackboard({"phase": "daily"})
        self.assertTrue(evaluate_guard(Guard("phase", "eq", "daily"), bb))
        self.assertFalse(evaluate_guard(Guard("phase", "eq", "shop"), bb))
        self.assertTrue(evaluate_guard(Guard("phase", "ne", "shop"), bb))

    def test_comparisons(self) -> None:
        bb = Blackboard({"n": 3})
        for op, value, expected in [
            ("lt", 5, True),
            ("lt", 3, False),
            ("le", 3, True),
            ("gt", 2, True),
            ("ge", 3, True),
            ("ge", 4, False),
        ]:
            self.assertEqual(
                evaluate_guard(Guard("n", op, value), bb),
                expected,
                f"{op}({value}) on n=3 -> {expected}",
            )

    def test_missing_vs_present(self) -> None:
        bb = Blackboard({"x": 0})
        self.assertTrue(evaluate_guard(Guard("y", "missing"), bb))
        self.assertFalse(evaluate_guard(Guard("x", "missing"), bb))
        self.assertTrue(evaluate_guard(Guard("x", "present"), bb))

    def test_truthy_falsy_require_key_present(self) -> None:
        # truthy/falsy on absent key is False (vacuous), not True — this
        # matches the contract in evaluate_guard.
        bb = Blackboard()
        self.assertFalse(evaluate_guard(Guard("x", "truthy"), bb))
        self.assertFalse(evaluate_guard(Guard("x", "falsy"), bb))
        bb.set("x", 0)
        self.assertFalse(evaluate_guard(Guard("x", "truthy"), bb))
        self.assertTrue(evaluate_guard(Guard("x", "falsy"), bb))

    def test_in_not_in(self) -> None:
        bb = Blackboard({"role": "admin"})
        self.assertTrue(evaluate_guard(Guard("role", "in", ["admin", "ops"]), bb))
        self.assertFalse(evaluate_guard(Guard("role", "in", ["user"]), bb))
        self.assertTrue(evaluate_guard(Guard("role", "not_in", ["user"]), bb))

    def test_invalid_op_rejected_at_construction(self) -> None:
        with self.assertRaises(ValueError):
            Guard(key="x", op="weird")

    def test_empty_key_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Guard(key="", op="truthy")

    def test_incomparable_values_dont_crash(self) -> None:
        bb = Blackboard({"x": "abc"})
        # "abc" < 5 raises TypeError in py3; evaluator swallows and returns False.
        self.assertFalse(evaluate_guard(Guard("x", "lt", 5), bb))


class GuardNodeSelectionTest(unittest.TestCase):
    def _plan_with_phased_menu(self) -> StatePlan:
        a = StateNode(
            state="S_MENU",
            action=ActionIntent(name="click_daily", kind="ui.click"),
            next_state="S_DAILY",
            guard=Guard("current_goal", "eq", "daily"),
        )
        b = StateNode(
            state="S_MENU",
            action=ActionIntent(name="click_shop", kind="ui.click"),
            next_state="S_SHOP",
            guard=Guard("current_goal", "eq", "shop"),
        )
        fallback = StateNode(
            state="S_MENU",
            action=ActionIntent(name="close", kind="ui.close"),
            next_state="S_DONE",
        )
        return StatePlan(
            initial_state="S_MENU",
            terminal_states=["S_DONE"],
            nodes=[a, b, fallback],
        )

    def test_node_for_picks_guard_matched(self) -> None:
        plan = self._plan_with_phased_menu()
        bb = Blackboard({"current_goal": "shop"})
        node = plan.node_for("S_MENU", bb)
        self.assertIsNotNone(node)
        self.assertEqual(node.action.name, "click_shop")

    def test_node_for_falls_through_to_unguarded(self) -> None:
        plan = self._plan_with_phased_menu()
        bb = Blackboard({"current_goal": "unknown_goal"})
        node = plan.node_for("S_MENU", bb)
        self.assertIsNotNone(node)
        # Neither daily nor shop matches; unguarded fallback wins.
        self.assertEqual(node.action.name, "close")

    def test_node_for_back_compat_without_blackboard(self) -> None:
        # Legacy callers that pass no blackboard still get a node —
        # they match the first unguarded node with the given name.
        plan = self._plan_with_phased_menu()
        node = plan.node_for("S_MENU")
        self.assertIsNotNone(node)
        self.assertEqual(node.action.name, "close")

    def test_node_for_unknown_state_returns_none(self) -> None:
        plan = self._plan_with_phased_menu()
        self.assertIsNone(plan.node_for("S_NOWHERE"))


class GuardSerializationTest(unittest.TestCase):
    def test_guard_roundtrip(self) -> None:
        g = Guard("counter", "lt", 5)
        payload = guard_to_dict(g)
        self.assertEqual(payload, {"key": "counter", "op": "lt", "value": 5})
        self.assertEqual(guard_from_dict(payload), g)

    def test_guard_to_dict_none(self) -> None:
        self.assertIsNone(guard_to_dict(None))
        self.assertIsNone(guard_from_dict(None))
        self.assertIsNone(guard_from_dict({}))
        self.assertIsNone(guard_from_dict({"key": ""}))

    def test_guard_from_dict_rejects_invalid_op(self) -> None:
        self.assertIsNone(guard_from_dict({"key": "x", "op": "zzz"}))

    def test_workflow_plan_roundtrip_preserves_guard(self) -> None:
        plan = StatePlan(
            initial_state="S_MENU",
            terminal_states=["S_DONE"],
            nodes=[
                StateNode(
                    state="S_MENU",
                    action=ActionIntent(name="a", kind="ui.click"),
                    next_state="S_DONE",
                    guard=Guard("goal", "eq", "daily"),
                ),
                StateNode(state="S_DONE"),
            ],
        )
        wp = WorkflowPlan(profile="p", game="g", scenario="s", state_plan=plan)
        payload = json.loads(json.dumps(wp.to_dict()))
        restored = WorkflowPlan.from_dict(payload)
        self.assertIsNotNone(restored.state_plan)
        g = restored.state_plan.nodes[0].guard
        self.assertIsNotNone(g)
        self.assertEqual(g.key, "goal")
        self.assertEqual(g.op, "eq")
        self.assertEqual(g.value, "daily")
        # Unguarded node survives with guard=None.
        self.assertIsNone(restored.state_plan.nodes[1].guard)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
