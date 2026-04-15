from __future__ import annotations

from src.adapters.action_specs import kongyue_claim_macro, launch_macro_update_ignore, one_dragon_drive_macro
from src.domain.run_request import RunRequest
from src.domain.workflow import ActionIntent, StateNode, StatePlan, WorkflowPlan, WorkflowStep
from src.ports.profile_port import AutomationProfilePort


class GenshinCloudBetterGIProfile(AutomationProfilePort):
    @property
    def profile_name(self) -> str:
        return "genshin_cloud_bettergi"

    def build_plan(self, request: RunRequest) -> WorkflowPlan:
        scenario = request.scenario or "daily_default"
        override = request.requested_policy_override

        queue_strategy = str(override.get("queue_strategy", "normal")).strip().lower()
        assistant_log_root = str(override.get("assistant_log_root", "")).strip()
        assistant_log_glob = str(override.get("assistant_log_glob", "*.log")).strip() or "*.log"

        shared_genshin = {
            "required_context": "genshin_window",
            "controller_id": "genshin_controller",
            "required_resources": ["mouse", "keyboard", "focus"],
            "transition_settle_seconds": float(override.get("transition_settle_seconds", 2.0)),
            "transition_timeout_seconds": float(override.get("transition_timeout_seconds", 60.0)),
            "transition_require_observed": bool(override.get("transition_require_observed", True)),
            "transition_observed_ticks": int(override.get("transition_observed_ticks", 3)),
        }
        shared_btgi = {
            "required_context": "bettergi_panel",
            "controller_id": "bettergi_controller",
            "required_resources": ["mouse", "keyboard", "focus"],
            "transition_settle_seconds": float(override.get("transition_settle_seconds", 2.0)),
            "transition_timeout_seconds": float(override.get("transition_timeout_seconds", 60.0)),
            "transition_require_observed": bool(override.get("transition_require_observed", True)),
            "transition_observed_ticks": int(override.get("transition_observed_ticks", 2)),
        }

        close_reward_steps = [
            {
                "op": "click_element",
                "element_id": "cloud_claim_gift_close",
                "element_profile": "genshin_cloud",
                "timeout_seconds": 2.0,
                "poll_seconds": 0.08,
            }
        ]
        click_start_game_steps = [
            {
                "op": "click_element",
                "element_id": "cloud_start_game_button",
                "element_profile": "genshin_cloud",
                "timeout_seconds": 2.0,
                "poll_seconds": 0.08,
            }
        ]
        queue_select_steps: list[dict[str, object]] = []
        if queue_strategy == "quick":
            queue_select_steps = [
                {
                    "op": "click_element",
                    "element_id": "cloud_queue_quick_button",
                    "element_profile": "genshin_cloud",
                    "timeout_seconds": 2.0,
                    "poll_seconds": 0.08,
                }
            ]
        elif queue_strategy != "none":
            queue_select_steps = [
                {
                    "op": "click_element",
                    "element_id": "cloud_queue_normal_button",
                    "element_profile": "genshin_cloud",
                    "timeout_seconds": 2.0,
                    "poll_seconds": 0.08,
                }
            ]

        click_enter_game_steps = [
            {
                "op": "click_element",
                "element_id": "cloud_door_enter",
                "element_profile": "genshin_cloud",
                "timeout_seconds": 18.0,
                "poll_seconds": 0.2,
                "clicks": 2,
            }
        ]
        kongyue_steps = kongyue_claim_macro()

        post_ready_macro_steps: list[dict[str, object]] = []
        launch_macro_steps = launch_macro_update_ignore()
        drive_macro_steps = one_dragon_drive_macro()

        wait_params = {
            "scene": "in_world",
            "timeout_seconds": float(override.get("game_ready_timeout_seconds", 240.0)),
            "ready_after_seconds": float(override.get("game_ready_after_seconds", 60.0)),
            "ready_element_id": str(override.get("ready_element_id", "cloud_door_enter")).strip(),
            "ready_element_profile": str(override.get("ready_element_profile", "genshin_cloud")).strip() or "genshin_cloud",
            **shared_genshin,
        }

        drive_params = {
            "scenario": scenario,
            "assistant_log_root": assistant_log_root,
            "assistant_log_glob": assistant_log_glob,
            "assistant_idle_seconds": float(override.get("assistant_idle_seconds", 45.0)),
            "assistant_timeout_seconds": float(override.get("assistant_timeout_seconds", 5400.0)),
            "assistant_require_log_activity": bool(override.get("assistant_require_log_activity", True)),
            "drive_macro_steps": drive_macro_steps,
            **shared_btgi,
        }

        steps = [
            WorkflowStep(name="start_cloud_game", kind="game.launch", params={**shared_genshin}),
            WorkflowStep(name="close_reward_popup", kind="game.queue.enter", params={"queue_macro_steps": close_reward_steps, **shared_genshin}),
            WorkflowStep(name="click_start_game", kind="game.queue.enter", params={"queue_macro_steps": click_start_game_steps, **shared_genshin}),
            WorkflowStep(name="select_queue", kind="game.queue.enter", params={"queue_macro_steps": queue_select_steps, **shared_genshin}),
            WorkflowStep(name="click_enter_game", kind="game.queue.enter", params={"queue_macro_steps": click_enter_game_steps, **shared_genshin}),
            WorkflowStep(name="claim_kongyue", kind="game.kongyue.claim", params={"kongyue_macro_steps": kongyue_steps, **shared_genshin}),
            WorkflowStep(name="wait_game_ready", kind="game.wait.scene", params={**wait_params, "post_ready_macro_steps": post_ready_macro_steps}),
            WorkflowStep(name="start_companion", kind="assistant.launch", params={"assistant": "bettergi", **shared_btgi}),
            WorkflowStep(
                name="dismiss_btgi_update",
                kind="assistant.launch",
                params={"assistant": "bettergi", "skip_start_process": True, "launch_macro_steps": launch_macro_steps, **shared_btgi},
            ),
            WorkflowStep(name="drive_companion", kind="assistant.drive", params=drive_params),
            WorkflowStep(name="collect_artifacts", kind="system.collect", params={**shared_btgi}),
        ]

        state_plan = StatePlan(
            initial_state="S_BOOTSTRAP",
            terminal_states=["S_DONE"],
            max_ticks=int(override.get("state_max_ticks", 300)),
            nodes=[
                StateNode(
                    state="S_BOOTSTRAP",
                    action=ActionIntent(
                        name="start_cloud_game",
                        kind="game.launch",
                        params={**shared_genshin},
                        controller_id="genshin_controller",
                        required_context="genshin_window",
                    ),
                    controller_id="genshin_controller",
                    context_id="genshin_window",
                    next_state="S_DISCOVER_CLOUD",
                    stable_ticks=1,
                    expected_next=("S_DISCOVER_CLOUD",),
                ),
                StateNode(
                    state="S_DISCOVER_CLOUD",
                    controller_id="genshin_controller",
                    context_id="genshin_window",
                    wait_seconds=0.12,
                    stable_ticks=1,
                    expected_next=(
                        "S_DAILY_REWARD_POPUP",
                        "S_CLOUD_HOME",
                        "S_QUEUEING",
                        "S_ENTER_PROMPT",
                        "S_KONGYUE",
                        "S_IN_GAME",
                    ),
                ),
                StateNode(
                    state="S_DAILY_REWARD_POPUP",
                    action=ActionIntent(
                        name="close_reward_popup",
                        kind="game.queue.enter",
                        params={"queue_macro_steps": close_reward_steps, **shared_genshin},
                        controller_id="genshin_controller",
                        required_context="genshin_window",
                    ),
                    controller_id="genshin_controller",
                    context_id="genshin_window",
                    next_state="S_DISCOVER_CLOUD",
                    stable_ticks=2,
                    expected_next=("S_DISCOVER_CLOUD", "S_CLOUD_HOME"),
                    recognition={
                        "profile": "genshin_cloud",
                        "expr": {
                            "op": "kof",
                            "k": 2,
                            "items": [
                                {"present": "cloud_daily_reward_keyword"},
                                {"present": "cloud_free_time_keyword"},
                                {"present": "cloud_click_blank_close_keyword"},
                            ],
                        },
                        "timeout_seconds": 0.10,
                        "poll_seconds": 0.03,
                    },
                ),
                StateNode(
                    state="S_CLOUD_HOME",
                    action=ActionIntent(
                        name="click_start_game",
                        kind="game.queue.enter",
                        params={"queue_macro_steps": click_start_game_steps, **shared_genshin},
                        controller_id="genshin_controller",
                        required_context="genshin_window",
                    ),
                    controller_id="genshin_controller",
                    context_id="genshin_window",
                    next_state="S_DISCOVER_CLOUD",
                    stable_ticks=2,
                    expected_next=("S_DISCOVER_CLOUD", "S_QUEUEING", "S_ENTER_PROMPT"),
                    recognition={
                        "profile": "genshin_cloud",
                        "expr": {"present": "cloud_start_game_button"},
                        "timeout_seconds": 0.10,
                        "poll_seconds": 0.03,
                    },
                ),
                StateNode(
                    state="S_QUEUEING",
                    controller_id="genshin_controller",
                    context_id="genshin_window",
                    wait_seconds=0.3,
                    stable_ticks=3,
                    expected_next=("S_QUEUEING", "S_ENTER_PROMPT"),
                    recognition={
                        "profile": "genshin_cloud",
                        "expr": {
                            "op": "all",
                            "items": [
                                {"present": "cloud_queue_exit_text"},
                                {"present": "cloud_queue_eta_text"},
                            ],
                        },
                        "timeout_seconds": 0.12,
                        "poll_seconds": 0.03,
                    },
                ),
                StateNode(
                    state="S_ENTER_PROMPT",
                    action=ActionIntent(
                        name="click_enter_game",
                        kind="game.queue.enter",
                        params={"queue_macro_steps": click_enter_game_steps, **shared_genshin},
                        max_retries=2,
                        backoff_seconds=1.5,
                        controller_id="genshin_controller",
                        required_context="genshin_window",
                    ),
                    controller_id="genshin_controller",
                    context_id="genshin_window",
                    next_state="S_DISCOVER_CLOUD",
                    stable_ticks=4,
                    expected_next=("S_DISCOVER_CLOUD", "S_KONGYUE", "S_IN_GAME"),
                    recognition={
                        "profile": "genshin_cloud",
                        "expr": {
                            "op": "all",
                            "items": [
                                {"absent": "cloud_queue_exit_text"},
                                {"absent": "cloud_queue_eta_text"},
                                {"present": "cloud_door_enter"},
                            ],
                        },
                        "timeout_seconds": 0.20,
                        "poll_seconds": 0.05,
                    },
                ),
                StateNode(
                    state="S_KONGYUE",
                    action=ActionIntent(
                        name="claim_kongyue",
                        kind="game.kongyue.claim",
                        params={"kongyue_macro_steps": kongyue_steps, **shared_genshin},
                        controller_id="genshin_controller",
                        required_context="genshin_window",
                    ),
                    controller_id="genshin_controller",
                    context_id="genshin_window",
                    next_state="S_DISCOVER_CLOUD",
                    stable_ticks=3,
                    expected_next=("S_DISCOVER_CLOUD", "S_IN_GAME"),
                    recognition={
                        "profile": "genshin_cloud",
                        "expr": {"present": "cloud_kongyue_reward_text"},
                        "timeout_seconds": 0.12,
                        "poll_seconds": 0.03,
                    },
                ),
                StateNode(
                    state="S_IN_GAME",
                    action=ActionIntent(
                        name="start_companion",
                        kind="assistant.launch",
                        params={"assistant": "bettergi", **shared_btgi},
                        controller_id="bettergi_controller",
                        required_context="bettergi_panel",
                    ),
                    controller_id="bettergi_controller",
                    context_id="bettergi_panel",
                    next_state="S_BTGI_DISCOVER",
                    stable_ticks=2,
                    expected_next=("S_BTGI_DISCOVER",),
                    recognition={
                        "profile": "genshin_cloud",
                        "expr": {
                            "op": "kof",
                            "k": 2,
                            "items": [
                                {"present": "cloud_in_game_num_1"},
                                {"present": "cloud_in_game_num_2"},
                                {"present": "cloud_in_game_num_3"},
                                {"present": "cloud_in_game_num_4"},
                            ],
                        },
                        "timeout_seconds": 0.10,
                        "poll_seconds": 0.03,
                    },
                ),
                StateNode(
                    state="S_BTGI_DISCOVER",
                    controller_id="bettergi_controller",
                    context_id="bettergi_panel",
                    wait_seconds=0.15,
                    stable_ticks=1,
                    expected_next=(
                        "S_BTGI_CHECK_UPDATE",
                        "S_BTGI_HOME",
                        "S_IN_GAME",
                    ),
                ),
                StateNode(
                    state="S_BTGI_CHECK_UPDATE",
                    action=ActionIntent(
                        name="dismiss_btgi_update",
                        kind="assistant.launch",
                        params={
                            "assistant": "bettergi",
                            "skip_start_process": True,
                            "launch_macro_steps": launch_macro_steps,
                            **shared_btgi,
                        },
                        controller_id="bettergi_controller",
                        required_context="bettergi_panel",
                    ),
                    controller_id="bettergi_controller",
                    context_id="bettergi_panel",
                    next_state="S_BTGI_DISCOVER",
                    stable_ticks=2,
                    expected_next=("S_BTGI_DISCOVER", "S_BTGI_HOME"),
                    recognition={
                        "profile": "bettergi",
                        "expr": {
                            "op": "any",
                            "items": [
                                {"present": "btgi_update_popup"},
                                {"present": "btgi_update_ignore_button"},
                            ],
                        },
                        "timeout_seconds": 0.10,
                        "poll_seconds": 0.03,
                    },
                ),
                StateNode(
                    state="S_BTGI_HOME",
                    action=ActionIntent(
                        name="drive_companion",
                        kind="assistant.drive",
                        params=drive_params,
                        controller_id="bettergi_controller",
                        required_context="bettergi_panel",
                    ),
                    controller_id="bettergi_controller",
                    context_id="bettergi_panel",
                    next_state="S_DONE",
                    stable_ticks=2,
                    expected_next=("S_DONE",),
                    recognition={
                        "profile": "bettergi",
                        "expr": {"present": "btgi_home"},
                        "timeout_seconds": 0.10,
                        "poll_seconds": 0.03,
                    },
                ),
            ],
        )

        return WorkflowPlan(
            profile=self.profile_name,
            game="genshin",
            scenario=scenario,
            mode="state_driven",
            state_plan=state_plan,
            steps=steps,
        )
