import unittest

from src.adapters.profiles import GenshinPCBetterGIProfile
from src.domain.run_request import RunRequest


class GenshinPCProfileTest(unittest.TestCase):
    def test_build_plan(self) -> None:
        p = GenshinPCBetterGIProfile()
        plan = p.build_plan(RunRequest(trigger="API", idempotency_key="k", target_profile="genshin_pc_bettergi"))
        self.assertEqual(plan.profile, "genshin_pc_bettergi")
        self.assertEqual(plan.game, "genshin_pc")
        names = [s.name for s in plan.steps]
        self.assertIn("start_pc_game", names)
        self.assertIn("drive_companion", names)


if __name__ == "__main__":
    unittest.main()
