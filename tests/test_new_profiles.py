import unittest

from src.adapters.profiles import BetterGIOneDragonProfile, GenshinCloudLaunchProfile
from src.domain.run_request import RunRequest


class NewProfilesTest(unittest.TestCase):
    def test_cloud_launch_profile_builds(self) -> None:
        p = GenshinCloudLaunchProfile()
        plan = p.build_plan(RunRequest(trigger="API", idempotency_key="k", target_profile="genshin_cloud_launch"))
        self.assertEqual(plan.profile, "genshin_cloud_launch")
        self.assertIsNotNone(plan.state_plan)
        self.assertEqual(plan.state_plan.initial_state, "S_CLOUD_BOOT")
        self.assertIn("S_CLOUD_IN_GAME", plan.state_plan.terminal_states)

    def test_bettergi_one_dragon_profile_builds(self) -> None:
        p = BetterGIOneDragonProfile()
        plan = p.build_plan(
            RunRequest(
                trigger="API",
                idempotency_key="k2",
                target_profile="bettergi_one_dragon",
                requested_policy_override={"assistant_log_root": "C:/Program Files/BetterGI/log"},
            )
        )
        self.assertEqual(plan.profile, "bettergi_one_dragon")
        self.assertIsNotNone(plan.state_plan)
        self.assertEqual(plan.state_plan.initial_state, "S_BTGI_BOOT")
        self.assertIn("S_BTGI_DONE", plan.state_plan.terminal_states)
        names = [s.name for s in plan.steps]
        self.assertIn("watch_one_dragon_until_idle", names)


if __name__ == "__main__":
    unittest.main()
