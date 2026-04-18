from __future__ import annotations

import unittest

from src.adapters.controllers import BlackboardController
from src.domain.workflow import WorkflowStep
from src.kernel.context_store import RunContext


class BlackboardControllerTest(unittest.TestCase):
    def _ctx(self) -> RunContext:
        return RunContext(run_id="r", manifest={})

    def test_supports_bb_kinds(self) -> None:
        c = BlackboardController()
        self.assertTrue(c.supports(WorkflowStep(name="x", kind="bb.set")))
        self.assertTrue(c.supports(WorkflowStep(name="x", kind="bb.inc")))
        self.assertTrue(c.supports(WorkflowStep(name="x", kind="bb.delete")))
        self.assertTrue(c.supports(WorkflowStep(name="x", kind="bb.clear")))
        self.assertFalse(c.supports(WorkflowStep(name="x", kind="ui.click")))

    def test_bb_set_writes_value(self) -> None:
        c = BlackboardController()
        ctx = self._ctx()
        res = c.execute(
            WorkflowStep(name="goal", kind="bb.set", params={"key": "current_goal", "value": "daily"}),
            ctx,
        )
        self.assertTrue(res["ok"])
        self.assertEqual(ctx.blackboard.get("current_goal"), "daily")

    def test_bb_inc_defaults_to_one(self) -> None:
        c = BlackboardController()
        ctx = self._ctx()
        res = c.execute(WorkflowStep(name="n", kind="bb.inc", params={"key": "counter"}), ctx)
        self.assertTrue(res["ok"])
        self.assertEqual(ctx.blackboard.get("counter"), 1)
        res = c.execute(
            WorkflowStep(name="n", kind="bb.inc", params={"key": "counter", "delta": 2}),
            ctx,
        )
        self.assertTrue(res["ok"])
        self.assertEqual(ctx.blackboard.get("counter"), 3)

    def test_bb_inc_rejects_bool_delta(self) -> None:
        c = BlackboardController()
        res = c.execute(
            WorkflowStep(name="n", kind="bb.inc", params={"key": "x", "delta": True}),
            self._ctx(),
        )
        self.assertFalse(res["ok"])
        self.assertEqual(res["detail"], "bb_inc_bad_delta")

    def test_bb_inc_surfaces_type_error(self) -> None:
        c = BlackboardController()
        ctx = self._ctx()
        ctx.blackboard.set("name", "alice")
        res = c.execute(WorkflowStep(name="n", kind="bb.inc", params={"key": "name"}), ctx)
        self.assertFalse(res["ok"])
        self.assertIn("bb_type_error", str(res["detail"]))

    def test_bb_delete_missing_key_is_ok(self) -> None:
        c = BlackboardController()
        ctx = self._ctx()
        res = c.execute(WorkflowStep(name="d", kind="bb.delete", params={"key": "absent"}), ctx)
        self.assertTrue(res["ok"])

    def test_bb_clear_wipes_everything(self) -> None:
        c = BlackboardController()
        ctx = self._ctx()
        ctx.blackboard.update({"a": 1, "b": 2})
        res = c.execute(WorkflowStep(name="c", kind="bb.clear"), ctx)
        self.assertTrue(res["ok"])
        self.assertFalse(ctx.blackboard.has("a"))
        self.assertFalse(ctx.blackboard.has("b"))

    def test_missing_key_rejected_for_mutating_kinds(self) -> None:
        c = BlackboardController()
        res = c.execute(WorkflowStep(name="x", kind="bb.set", params={}), self._ctx())
        self.assertFalse(res["ok"])
        self.assertEqual(res["detail"], "bb_missing_key")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
