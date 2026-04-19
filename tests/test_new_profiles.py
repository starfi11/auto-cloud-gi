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

    def test_bettergi_one_dragon_topology_matches_tmp1(self) -> None:
        p = BetterGIOneDragonProfile()
        plan = p.build_plan(
            RunRequest(
                trigger="API",
                idempotency_key="k3",
                target_profile="bettergi_one_dragon",
                requested_policy_override={"assistant_log_root": "C:/Program Files/BetterGI/log"},
            )
        )
        self.assertIsNotNone(plan.state_plan)
        nodes = {n.state: n for n in plan.state_plan.nodes}

        # tmp1: 最初状态 -> bettergi更新弹窗界面|bettergi首页
        boot = nodes["S_BTGI_BOOT"]
        self.assertIsNotNone(boot.action)
        self.assertEqual(boot.action.name, "launch_bettergi")
        self.assertEqual(boot.next_state, "S_BTGI_UPDATE_POPUP")
        self.assertEqual(boot.expected_next, ("S_BTGI_UPDATE_POPUP", "S_BTGI_HOME"))

        # tmp1: bettergi更新弹窗界面 -> bettergi首页
        popup = nodes["S_BTGI_UPDATE_POPUP"]
        self.assertIsNotNone(popup.action)
        self.assertEqual(popup.action.name, "dismiss_btgi_update")
        self.assertEqual(popup.next_state, "S_BTGI_HOME")
        self.assertEqual(popup.expected_next, ("S_BTGI_HOME",))

        # tmp1: bettergi首页 -> 等待调整捕获窗口的状态
        home = nodes["S_BTGI_HOME"]
        self.assertIsNotNone(home.action)
        self.assertEqual(home.action.name, "prepare_capture_dropdown")
        self.assertEqual(home.next_state, "S_BTGI_CAPTURE_WAIT")
        self.assertEqual(home.expected_next, ("S_BTGI_CAPTURE_WAIT",))

        # tmp1: 等待调整捕获窗口的状态 -> 一条龙页面
        capture = nodes["S_BTGI_CAPTURE_WAIT"]
        self.assertIsNotNone(capture.action)
        self.assertEqual(capture.action.name, "adjust_capture_and_open_one_dragon")
        self.assertEqual(capture.next_state, "S_BTGI_ONE_DRAGON_PAGE")
        self.assertEqual(capture.expected_next, ("S_BTGI_ONE_DRAGON_PAGE",))

        # tmp1: 一条龙页面 -> 一条龙成功拉起状态
        dragon_page = nodes["S_BTGI_ONE_DRAGON_PAGE"]
        self.assertIsNotNone(dragon_page.action)
        self.assertEqual(dragon_page.action.name, "start_one_dragon")
        self.assertEqual(dragon_page.next_state, "S_BTGI_ONE_DRAGON_STARTED")
        self.assertEqual(dragon_page.expected_next, ("S_BTGI_ONE_DRAGON_STARTED",))

        # tmp1: 一条龙成功拉起状态 -> 一条龙结束状态
        started = nodes["S_BTGI_ONE_DRAGON_STARTED"]
        self.assertIsNotNone(started.action)
        self.assertEqual(started.action.name, "watch_one_dragon_until_idle")
        self.assertEqual(started.next_state, "S_BTGI_DONE")
        self.assertEqual(started.expected_next, ("S_BTGI_DONE",))


if __name__ == "__main__":
    unittest.main()
