from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.adapters.action_specs import (
    adjust_capture_and_open_one_dragon_macro,
    kongyue_claim_macro,
    launch_macro_update_ignore,
    prepare_capture_dropdown_macro,
    start_one_dragon_macro,
)
from src.domain.workflow import ActionIntent, StateNode, WorkflowStep


@dataclass(frozen=True)
class ProfileSegment:
    initial_state: str
    done_state: str
    nodes: list[StateNode]
    steps: list[WorkflowStep]


def build_cloud_segment(
    override: dict[str, Any],
    *,
    handoff_to: str | None = None,
) -> ProfileSegment:
    queue_strategy = str(override.get("queue_strategy", "normal")).strip().lower()

    shared_genshin = {
        "required_context": "genshin_window",
        "controller_id": "genshin_controller",
        "required_resources": ["mouse", "keyboard", "focus"],
        "transition_settle_seconds": float(override.get("transition_settle_seconds", 2.0)),
        "transition_timeout_seconds": float(override.get("transition_timeout_seconds", 60.0)),
        "transition_require_observed": bool(override.get("transition_require_observed", True)),
        "transition_observed_ticks": int(override.get("transition_observed_ticks", 2)),
        "transition_observe_interval_seconds": max(
            1.1, float(override.get("transition_observe_interval_seconds", 1.2))
        ),
    }

    # 文档语义：启动后可能直接在首页，也可能先弹每日奖励。
    # 用 optional 关闭动作吸收分支差异，避免引入统一分流枢纽状态。
    close_reward_steps = [
        {
            "op": "click_element",
            "element_id": "cloud_claim_gift_close",
            "element_profile": "genshin_cloud",
            "timeout_seconds": 2.0,
            "poll_seconds": 0.08,
            "optional": True,
        }
    ]
    click_start_game_steps = [
        {
            "op": "click_element",
            "element_id": "cloud_start_game_button",
            "element_profile": "genshin_cloud",
            "timeout_seconds": 2.5,
            "poll_seconds": 0.08,
        }
    ]

    queue_select_steps: list[dict[str, object]]
    if queue_strategy == "quick":
        queue_select_steps = [
            {
                "op": "click_element",
                "element_id": "cloud_queue_quick_button",
                "element_profile": "genshin_cloud",
                "timeout_seconds": 2.0,
                "poll_seconds": 0.08,
                "optional": True,
            }
        ]
    else:
        queue_select_steps = [
            {
                "op": "click_element",
                "element_id": "cloud_queue_normal_button",
                "element_profile": "genshin_cloud",
                "timeout_seconds": 2.0,
                "poll_seconds": 0.08,
                "optional": True,
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

    raw_kongyue = kongyue_claim_macro()
    kongyue_steps = [{**s, "optional": True} for s in raw_kongyue]

    queue_wait_params = {
        "scene": "queue_wait",
        "timeout_seconds": float(override.get("queue_wait_timeout_seconds", 300.0)),
        "text_poll_seconds": max(1.1, float(override.get("queue_wait_poll_seconds", 1.2))),
        "ready_element_id": "cloud_door_icon",
        "ready_element_profile": "genshin_cloud",
        "element_poll_window_seconds": float(override.get("queue_wait_element_poll_window_seconds", 1.0)),
        **shared_genshin,
    }

    in_game_wait_params = {
        "scene": "in_game",
        "timeout_seconds": float(override.get("in_game_wait_timeout_seconds", 120.0)),
        "text_poll_seconds": max(1.1, float(override.get("in_game_wait_poll_seconds", 1.2))),
        "ready_element_id": "cloud_ingame_bag_icon",
        "ready_element_profile": "genshin_cloud",
        "element_poll_window_seconds": float(override.get("in_game_element_poll_window_seconds", 0.8)),
        **shared_genshin,
    }

    nodes = [
        StateNode(
            state="S_CLOUD_BOOT",
            action=ActionIntent(
                name="start_cloud_game",
                kind="game.launch",
                params={**shared_genshin},
                controller_id="genshin_controller",
                required_context="genshin_window",
            ),
            controller_id="genshin_controller",
            context_id="genshin_window",
            next_state="S_CLOUD_DAILY_REWARD",
            stable_ticks=1,
            expected_next=("S_CLOUD_DAILY_REWARD", "S_CLOUD_HOME"),
            recoverability="safe_reentry",
        ),
        StateNode(
            state="S_CLOUD_DAILY_REWARD",
            action=ActionIntent(
                name="close_reward_popup",
                kind="game.queue.enter",
                params={"queue_macro_steps": close_reward_steps, **shared_genshin},
                controller_id="genshin_controller",
                required_context="genshin_window",
            ),
            controller_id="genshin_controller",
            context_id="genshin_window",
            next_state="S_CLOUD_HOME",
            stable_ticks=1,
            expected_next=("S_CLOUD_HOME",),
            recognition={
                "profile": "genshin_cloud",
                "expr": {
                    "op": "any",
                    "items": [
                        {"present": "cloud_daily_reward_keyword"},
                        {"present": "cloud_free_time_keyword"},
                        {"present": "cloud_click_blank_close_keyword"},
                    ],
                },
            },
            recoverability="safe_reentry",
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
            next_state="S_CLOUD_QUEUE_SELECT",
            stable_ticks=1,
            expected_next=(
                "S_CLOUD_QUEUE_SELECT",
                "S_CLOUD_QUEUE_WAIT",
                "S_CLOUD_DOOR",
            ),
            recognition={
                "profile": "genshin_cloud",
                "expr": {
                    "op": "any",
                    "items": [
                        {"present": "cloud_start_game_button"},
                        {
                            "op": "all",
                            "items": [
                                {"present": "cloud_start_game_button"},
                                {"present": "cloud_home_genshin_logo"},
                            ],
                        },
                    ],
                },
            },
            recoverability="safe_reentry",
        ),
        StateNode(
            state="S_CLOUD_QUEUE_SELECT",
            action=ActionIntent(
                name="select_queue",
                kind="game.queue.enter",
                params={"queue_macro_steps": queue_select_steps, **shared_genshin},
                controller_id="genshin_controller",
                required_context="genshin_window",
            ),
            controller_id="genshin_controller",
            context_id="genshin_window",
            next_state="S_CLOUD_QUEUE_WAIT",
            stable_ticks=1,
            expected_next=("S_CLOUD_QUEUE_WAIT", "S_CLOUD_DOOR"),
            recognition={
                "profile": "genshin_cloud",
                "expr": {
                    "op": "any",
                    "items": [
                        {"present": "cloud_queue_select_title"},
                        {"present": "cloud_queue_quick_button"},
                        {"present": "cloud_queue_normal_button"},
                    ],
                },
            },
            recoverability="safe_reentry",
        ),
        StateNode(
            state="S_CLOUD_QUEUE_WAIT",
            action=ActionIntent(
                name="wait_queue_finish",
                kind="game.wait.scene",
                params={**queue_wait_params},
                controller_id="genshin_controller",
                required_context="genshin_window",
            ),
            controller_id="genshin_controller",
            context_id="genshin_window",
            next_state="S_CLOUD_DOOR",
            stable_ticks=1,
            expected_next=("S_CLOUD_DOOR",),
            recognition={
                "profile": "genshin_cloud",
                "expr": {
                    "op": "any",
                    "items": [
                        {"present": "cloud_queue_exit_text"},
                        {"present": "cloud_queue_eta_text"},
                    ],
                },
            },
            recoverability="safe_reentry",
        ),
        StateNode(
            state="S_CLOUD_DOOR",
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
            next_state="S_CLOUD_KONGYUE",
            stable_ticks=1,
            expected_next=("S_CLOUD_KONGYUE", "S_CLOUD_IN_GAME_WAIT"),
            recognition={
                "profile": "genshin_cloud",
                "expr": {
                    "op": "any",
                    "items": [
                        {"present": "cloud_door_enter"},
                        {
                            "op": "all",
                            "items": [
                                {"present": "cloud_door_enter"},
                                {"present": "cloud_door_icon"},
                            ],
                        },
                    ],
                },
            },
            recoverability="safe_reentry",
        ),
        StateNode(
            state="S_CLOUD_KONGYUE",
            action=ActionIntent(
                name="claim_kongyue",
                kind="game.kongyue.claim",
                params={"kongyue_macro_steps": kongyue_steps, **shared_genshin},
                controller_id="genshin_controller",
                required_context="genshin_window",
            ),
            controller_id="genshin_controller",
            context_id="genshin_window",
            next_state="S_CLOUD_IN_GAME_WAIT",
            stable_ticks=1,
            expected_next=("S_CLOUD_IN_GAME_WAIT",),
            recognition={
                "profile": "genshin_cloud",
                "expr": {"present": "cloud_kongyue_reward_text"},
            },
            recoverability="safe_reentry",
        ),
        StateNode(
            state="S_CLOUD_IN_GAME_WAIT",
            action=ActionIntent(
                name="wait_in_game_ready",
                kind="game.wait.scene",
                params={**in_game_wait_params},
                controller_id="genshin_controller",
                required_context="genshin_window",
            ),
            controller_id="genshin_controller",
            context_id="genshin_window",
            next_state="S_CLOUD_IN_GAME",
            stable_ticks=1,
            expected_next=("S_CLOUD_IN_GAME",),
            recognition={
                "profile": "genshin_cloud",
                "expr": {
                    "op": "any",
                    "items": [
                        {"present": "cloud_ingame_bag_icon"},
                        {
                            "op": "all",
                            "items": [
                                {"present": "cloud_ingame_bag_icon"},
                                {"present": "cloud_uid_text"},
                            ],
                        },
                    ],
                },
            },
            recoverability="safe_reentry",
        ),
        StateNode(
            state="S_CLOUD_IN_GAME",
            controller_id="genshin_controller",
            context_id="genshin_window",
            next_state=handoff_to,
            stable_ticks=1,
            wait_seconds=0.15,
            expected_next=((handoff_to,) if handoff_to else None),
            recognition={
                "profile": "genshin_cloud",
                "expr": {
                    "op": "any",
                    "items": [
                        {"present": "cloud_ingame_bag_icon"},
                        {
                            "op": "all",
                            "items": [
                                {"present": "cloud_ingame_bag_icon"},
                                {"present": "cloud_uid_text"},
                            ],
                        },
                    ],
                },
            },
            recoverability="safe_reentry",
        ),
    ]

    steps = [
        WorkflowStep(name="start_cloud_game", kind="game.launch", params={**shared_genshin}),
        WorkflowStep(name="close_reward_popup", kind="game.queue.enter", params={"queue_macro_steps": close_reward_steps, **shared_genshin}),
        WorkflowStep(name="click_start_game", kind="game.queue.enter", params={"queue_macro_steps": click_start_game_steps, **shared_genshin}),
        WorkflowStep(name="select_queue", kind="game.queue.enter", params={"queue_macro_steps": queue_select_steps, **shared_genshin}),
        WorkflowStep(name="wait_queue_finish", kind="game.wait.scene", params={**queue_wait_params}),
        WorkflowStep(name="click_enter_game", kind="game.queue.enter", params={"queue_macro_steps": click_enter_game_steps, **shared_genshin}),
        WorkflowStep(name="claim_kongyue", kind="game.kongyue.claim", params={"kongyue_macro_steps": kongyue_steps, **shared_genshin}),
        WorkflowStep(name="wait_in_game_ready", kind="game.wait.scene", params={**in_game_wait_params}),
    ]

    return ProfileSegment(
        initial_state="S_CLOUD_BOOT",
        done_state="S_CLOUD_IN_GAME",
        nodes=nodes,
        steps=steps,
    )


def build_btgi_segment(
    override: dict[str, Any],
    *,
    scenario: str,
    done_next_state: str | None = None,
) -> ProfileSegment:
    assistant_log_root = str(override.get("assistant_log_root", "")).strip()
    assistant_log_glob = str(override.get("assistant_log_glob", "*.log")).strip() or "*.log"

    shared_btgi = {
        "required_context": "bettergi_panel",
        "controller_id": "bettergi_controller",
        "required_resources": ["mouse", "keyboard", "focus"],
        "transition_settle_seconds": float(override.get("transition_settle_seconds", 2.0)),
        "transition_timeout_seconds": float(override.get("transition_timeout_seconds", 60.0)),
        "transition_require_observed": bool(override.get("transition_require_observed", True)),
        "transition_observed_ticks": int(override.get("transition_observed_ticks", 2)),
        "transition_observe_interval_seconds": max(
            1.1, float(override.get("transition_observe_interval_seconds", 1.2))
        ),
    }

    launch_focus_steps = [
        {"op": "sleep", "seconds": float(override.get("btgi_launch_wait_seconds", 10.0))},
        {"op": "hotkey", "keys": ["alt", "tab"], "after_sleep": 0.6},
    ]
    update_ignore_steps = launch_macro_update_ignore()
    prepare_dropdown_steps = prepare_capture_dropdown_macro()
    adjust_capture_steps = adjust_capture_and_open_one_dragon_macro()
    start_one_dragon_steps = start_one_dragon_macro()
    probe_drive_steps = [{"op": "sleep", "seconds": 0.05}]

    monitor_params = {
        "scenario": scenario,
        "assistant_log_root": assistant_log_root,
        "assistant_log_glob": assistant_log_glob,
        "assistant_idle_seconds": float(override.get("assistant_idle_seconds", 45.0)),
        "assistant_timeout_seconds": float(override.get("assistant_timeout_seconds", 900.0)),
        "assistant_require_log_activity": bool(override.get("assistant_require_log_activity", True)),
        "drive_macro_steps": probe_drive_steps,
        **shared_btgi,
    }

    nodes = [
        StateNode(
            state="S_BTGI_BOOT",
            action=ActionIntent(
                name="launch_bettergi",
                kind="assistant.launch",
                params={"assistant": "bettergi", "launch_macro_steps": launch_focus_steps, **shared_btgi},
                controller_id="bettergi_controller",
                required_context="bettergi_panel",
            ),
            controller_id="bettergi_controller",
            context_id="bettergi_panel",
            next_state="S_BTGI_UPDATE_POPUP",
            stable_ticks=1,
            expected_next=("S_BTGI_UPDATE_POPUP", "S_BTGI_HOME"),
            recoverability="safe_reentry",
        ),
        StateNode(
            state="S_BTGI_UPDATE_POPUP",
            action=ActionIntent(
                name="dismiss_btgi_update",
                kind="assistant.launch",
                params={
                    "assistant": "bettergi",
                    "skip_start_process": True,
                    "launch_macro_steps": update_ignore_steps,
                    **shared_btgi,
                },
                controller_id="bettergi_controller",
                required_context="bettergi_panel",
            ),
            controller_id="bettergi_controller",
            context_id="bettergi_panel",
            next_state="S_BTGI_HOME",
            stable_ticks=1,
            expected_next=("S_BTGI_HOME",),
            recognition={
                "profile": "bettergi",
                "expr": {
                    "op": "any",
                    "items": [
                        {"present": "btgi_update_popup"},
                        {"present": "btgi_update_ignore_button"},
                    ],
                },
            },
            recoverability="safe_reentry",
        ),
        StateNode(
            state="S_BTGI_HOME",
            action=ActionIntent(
                name="prepare_capture_dropdown",
                kind="assistant.launch",
                params={
                    "assistant": "bettergi",
                    "skip_start_process": True,
                    "launch_macro_steps": prepare_dropdown_steps,
                    **shared_btgi,
                },
                controller_id="bettergi_controller",
                required_context="bettergi_panel",
            ),
            controller_id="bettergi_controller",
            context_id="bettergi_panel",
            next_state="S_BTGI_CAPTURE_WAIT",
            stable_ticks=1,
            expected_next=("S_BTGI_CAPTURE_WAIT",),
            recognition={
                "profile": "bettergi",
                "expr": {
                    "op": "any",
                    "items": [
                        {"present": "btgi_home"},
                        {"present": "btgi_home_title"},
                        {"present": "btgi_home_subtitle"},
                    ],
                },
            },
            recoverability="safe_reentry",
        ),
        StateNode(
            state="S_BTGI_CAPTURE_WAIT",
            action=ActionIntent(
                name="adjust_capture_and_open_one_dragon",
                kind="assistant.launch",
                params={
                    "assistant": "bettergi",
                    "skip_start_process": True,
                    "launch_macro_steps": adjust_capture_steps,
                    **shared_btgi,
                },
                controller_id="bettergi_controller",
                required_context="bettergi_panel",
            ),
            controller_id="bettergi_controller",
            context_id="bettergi_panel",
            next_state="S_BTGI_ONE_DRAGON_PAGE",
            stable_ticks=1,
            expected_next=("S_BTGI_ONE_DRAGON_PAGE",),
            recognition={
                "profile": "bettergi",
                "expr": {"present": "btgi_capture_select_window"},
            },
            recoverability="safe_reentry",
        ),
        StateNode(
            state="S_BTGI_ONE_DRAGON_PAGE",
            action=ActionIntent(
                name="start_one_dragon",
                kind="assistant.launch",
                params={
                    "assistant": "bettergi",
                    "skip_start_process": True,
                    "launch_macro_steps": start_one_dragon_steps,
                    **shared_btgi,
                },
                controller_id="bettergi_controller",
                required_context="bettergi_panel",
            ),
            controller_id="bettergi_controller",
            context_id="bettergi_panel",
            next_state="S_BTGI_ONE_DRAGON_STARTED",
            stable_ticks=1,
            expected_next=("S_BTGI_ONE_DRAGON_STARTED",),
            recognition={
                "profile": "bettergi",
                "expr": {
                    "op": "any",
                    "items": [
                        {"present": "btgi_task_list"},
                        {"present": "btgi_config_label"},
                    ],
                },
            },
            recoverability="safe_reentry",
        ),
        StateNode(
            state="S_BTGI_ONE_DRAGON_STARTED",
            action=ActionIntent(
                name="watch_one_dragon_until_idle",
                kind="assistant.drive",
                params=monitor_params,
                controller_id="bettergi_controller",
                required_context="bettergi_panel",
            ),
            controller_id="bettergi_controller",
            context_id="bettergi_panel",
            next_state="S_BTGI_DONE",
            stable_ticks=1,
            expected_next=("S_BTGI_DONE",),
            recoverability="transient",
        ),
        StateNode(
            state="S_BTGI_DONE",
            controller_id="bettergi_controller",
            context_id="bettergi_panel",
            next_state=done_next_state,
            stable_ticks=1,
            wait_seconds=0.1,
            expected_next=((done_next_state,) if done_next_state else None),
            recoverability="safe_reentry",
        ),
    ]

    steps = [
        WorkflowStep(
            name="launch_bettergi",
            kind="assistant.launch",
            params={"assistant": "bettergi", "launch_macro_steps": launch_focus_steps, **shared_btgi},
        ),
        WorkflowStep(
            name="dismiss_btgi_update",
            kind="assistant.launch",
            params={"assistant": "bettergi", "skip_start_process": True, "launch_macro_steps": update_ignore_steps, **shared_btgi},
        ),
        WorkflowStep(
            name="prepare_capture_dropdown",
            kind="assistant.launch",
            params={"assistant": "bettergi", "skip_start_process": True, "launch_macro_steps": prepare_dropdown_steps, **shared_btgi},
        ),
        WorkflowStep(
            name="adjust_capture_and_open_one_dragon",
            kind="assistant.launch",
            params={"assistant": "bettergi", "skip_start_process": True, "launch_macro_steps": adjust_capture_steps, **shared_btgi},
        ),
        WorkflowStep(
            name="start_one_dragon",
            kind="assistant.launch",
            params={"assistant": "bettergi", "skip_start_process": True, "launch_macro_steps": start_one_dragon_steps, **shared_btgi},
        ),
        WorkflowStep(name="watch_one_dragon_until_idle", kind="assistant.drive", params=monitor_params),
    ]

    return ProfileSegment(
        initial_state="S_BTGI_BOOT",
        done_state="S_BTGI_DONE",
        nodes=nodes,
        steps=steps,
    )
