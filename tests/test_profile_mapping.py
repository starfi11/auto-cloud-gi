import unittest

from src.adapters.profiles import GenshinCloudBetterGIProfile
from src.domain.run_request import RunRequest


class ProfileMappingTest(unittest.TestCase):
    def test_profile_injects_queue_strategy_and_assistant_log_watch(self) -> None:
        profile = GenshinCloudBetterGIProfile()
        plan = profile.build_plan(
            RunRequest(
                trigger="API_TRIGGER",
                idempotency_key="k",
                requested_policy_override={
                    "queue_strategy": "quick",
                    "assistant_log_root": "C:/Program Files/BetterGI/log",
                    "assistant_log_glob": "better-genshin-impact*.log",
                },
            )
        )
        enter_step = [s for s in plan.steps if s.name == "enter_queue"][0]
        drive_step = [s for s in plan.steps if s.name == "drive_companion"][0]
        self.assertEqual(enter_step.params.get("strategy"), "quick")
        self.assertIn("assistant_log_root", drive_step.params)
        self.assertIn("assistant_log_glob", drive_step.params)


if __name__ == "__main__":
    unittest.main()
