from __future__ import annotations

import unittest

from src.domain.blackboard import Blackboard, Guard
from src.domain.scenario import Goal, ScenarioSpec, advance_scenario


class ScenarioAdvanceTest(unittest.TestCase):
    def test_empty_scenario_marks_done(self) -> None:
        bb = Blackboard()
        self.assertIsNone(advance_scenario(ScenarioSpec(name="s"), bb))
        self.assertTrue(bb.get("_scenario_done"))
        self.assertFalse(bb.has("current_goal"))

    def test_installs_first_goal(self) -> None:
        spec = ScenarioSpec(
            name="daily",
            goals=[
                Goal("daily", until=Guard("daily_done", "truthy")),
                Goal("shop", until=Guard("shop_done", "truthy")),
            ],
        )
        bb = Blackboard()
        self.assertEqual(advance_scenario(spec, bb), "daily")
        self.assertEqual(bb.get("current_goal"), "daily")

    def test_advances_when_until_passes(self) -> None:
        spec = ScenarioSpec(
            name="s",
            goals=[
                Goal("a", until=Guard("a_done", "truthy")),
                Goal("b", until=Guard("b_done", "truthy")),
            ],
        )
        bb = Blackboard()
        self.assertEqual(advance_scenario(spec, bb), "a")
        bb.set("a_done", True)
        self.assertEqual(advance_scenario(spec, bb), "b")
        self.assertEqual(bb.get("current_goal"), "b")

    def test_finishes_when_last_until_passes(self) -> None:
        spec = ScenarioSpec(
            name="s",
            goals=[Goal("a", until=Guard("a_done", "truthy"))],
        )
        bb = Blackboard()
        advance_scenario(spec, bb)
        bb.set("a_done", True)
        self.assertIsNone(advance_scenario(spec, bb))
        self.assertTrue(bb.get("_scenario_done"))

    def test_one_shot_goal_advances_immediately(self) -> None:
        # Goal with until=None is one-shot: used for "setup" goals that
        # don't have a clean blackboard signal, just need to fire once.
        spec = ScenarioSpec(
            name="s",
            goals=[
                Goal("setup"),
                Goal("main", until=Guard("main_done", "truthy")),
            ],
        )
        bb = Blackboard()
        self.assertEqual(advance_scenario(spec, bb), "main")

    def test_idempotent_when_no_guard_flip(self) -> None:
        spec = ScenarioSpec(
            name="s",
            goals=[Goal("a", until=Guard("a_done", "truthy"))],
        )
        bb = Blackboard()
        advance_scenario(spec, bb)
        v = bb.version
        advance_scenario(spec, bb)
        self.assertEqual(bb.version, v, "no mutation when goal hasn't progressed")

    def test_recovers_from_unknown_current_goal(self) -> None:
        # Blackboard got nuked mid-run (e.g. recovery cleared it).
        spec = ScenarioSpec(
            name="s",
            goals=[Goal("a", until=Guard("a_done", "truthy"))],
        )
        bb = Blackboard({"current_goal": "ghost"})
        self.assertEqual(advance_scenario(spec, bb), "a")


class ScenarioSerializationTest(unittest.TestCase):
    def test_roundtrip(self) -> None:
        spec = ScenarioSpec(
            name="daily",
            goals=[
                Goal("daily", until=Guard("daily_done", "truthy")),
                Goal("setup"),
            ],
        )
        payload = spec.to_dict()
        restored = ScenarioSpec.from_dict(payload)
        self.assertEqual(restored.name, "daily")
        self.assertEqual(len(restored.goals), 2)
        self.assertEqual(restored.goals[0].name, "daily")
        self.assertIsNotNone(restored.goals[0].until)
        self.assertEqual(restored.goals[0].until.key, "daily_done")
        self.assertIsNone(restored.goals[1].until)

    def test_from_dict_rejects_malformed_goal(self) -> None:
        spec = ScenarioSpec.from_dict(
            {"name": "x", "goals": [{"name": ""}, "not a dict", {"name": "ok"}]}
        )
        self.assertEqual([g.name for g in spec.goals], ["ok"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
