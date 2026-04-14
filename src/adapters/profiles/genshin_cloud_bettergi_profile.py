from __future__ import annotations

from src.adapters.action_specs import launch_macro_update_ignore, post_ready_macro
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

        wait_params = {"scene": "in_world", "timeout_seconds": 240.0, "ready_after_seconds": 60.0}
        if scenario.startswith("debug_slow"):
            wait_params = {"scene": "in_world", "timeout_seconds": 30.0, "ready_after_seconds": 10.0}
        if bool(override.get("use_text_signal_wait", False)):
            wait_params.update(
                {
                    "scene_ready_text_any": ["点击进入"],
                    "scene_block_text_any": ["网络较差", "重新连接"],
                    "text_signal_file": str(override.get("text_signal_file", "./runtime/vision/signals/latest.txt")),
                    "text_poll_seconds": float(override.get("text_poll_seconds", 0.3)),
                }
            )

        shared_genshin = {
            "required_context": "genshin_window",
            "controller_id": "genshin_controller",
            "required_resources": ["mouse", "keyboard", "focus"],
        }
        shared_btgi = {
            "required_context": "bettergi_panel",
            "controller_id": "bettergi_controller",
            "required_resources": ["mouse", "keyboard", "focus"],
        }

        post_ready_macro_steps = post_ready_macro()

        launch_macro_steps = launch_macro_update_ignore()

        drive_params = {
            "scenario": scenario,
            "assistant_log_root": assistant_log_root,
            "assistant_log_glob": assistant_log_glob,
            "assistant_idle_seconds": float(override.get("assistant_idle_seconds", 45.0)),
            "assistant_timeout_seconds": float(override.get("assistant_timeout_seconds", 5400.0)),
            "assistant_require_log_activity": bool(override.get("assistant_require_log_activity", True)),
            **shared_btgi,
        }

        steps = [
            WorkflowStep(name="start_cloud_game", kind="game.launch", params={**shared_genshin}),
            WorkflowStep(name="enter_queue", kind="game.queue.enter", params={"strategy": queue_strategy or "normal", **shared_genshin}),
            WorkflowStep(
                name="wait_game_ready",
                kind="game.wait.scene",
                params={**wait_params, "post_ready_macro_steps": post_ready_macro_steps, **shared_genshin},
            ),
            WorkflowStep(
                name="start_companion",
                kind="assistant.launch",
                params={"assistant": "bettergi", "launch_macro_steps": launch_macro_steps, **shared_btgi},
            ),
            WorkflowStep(name="drive_companion", kind="assistant.drive", params=drive_params),
            WorkflowStep(name="collect_artifacts", kind="system.collect", params={**shared_btgi}),
        ]

        state_plan = StatePlan(
            initial_state="S_BOOTSTRAP",
            terminal_states=["S_DONE"],
            max_ticks=120,
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
                    next_state="S_QUEUE_ENTRY",
                ),
                StateNode(
                    state="S_QUEUE_ENTRY",
                    action=ActionIntent(
                        name="enter_queue",
                        kind="game.queue.enter",
                        params={"strategy": queue_strategy or "normal", **shared_genshin},
                        controller_id="genshin_controller",
                        required_context="genshin_window",
                    ),
                    controller_id="genshin_controller",
                    context_id="genshin_window",
                    next_state="S_WAIT_GAME_READY",
                ),
                StateNode(
                    state="S_WAIT_GAME_READY",
                    action=ActionIntent(
                        name="wait_game_ready",
                        kind="game.wait.scene",
                        params={**wait_params, "post_ready_macro_steps": post_ready_macro_steps, **shared_genshin},
                        controller_id="genshin_controller",
                        required_context="genshin_window",
                    ),
                    controller_id="genshin_controller",
                    context_id="genshin_window",
                    next_state="S_START_ASSISTANT",
                ),
                StateNode(
                    state="S_START_ASSISTANT",
                    action=ActionIntent(
                        name="start_companion",
                        kind="assistant.launch",
                        params={"assistant": "bettergi", "launch_macro_steps": launch_macro_steps, **shared_btgi},
                        controller_id="bettergi_controller",
                        required_context="bettergi_panel",
                    ),
                    controller_id="bettergi_controller",
                    context_id="bettergi_panel",
                    next_state="S_DRIVE_ASSISTANT",
                ),
                StateNode(
                    state="S_DRIVE_ASSISTANT",
                    action=ActionIntent(
                        name="drive_companion",
                        kind="assistant.drive",
                        params=drive_params,
                        controller_id="bettergi_controller",
                        required_context="bettergi_panel",
                    ),
                    controller_id="bettergi_controller",
                    context_id="bettergi_panel",
                    next_state="S_COLLECT",
                ),
                StateNode(
                    state="S_COLLECT",
                    action=ActionIntent(
                        name="collect_artifacts",
                        kind="system.collect",
                        params={**shared_btgi},
                        controller_id="bettergi_controller",
                        required_context="bettergi_panel",
                    ),
                    controller_id="bettergi_controller",
                    context_id="bettergi_panel",
                    next_state="S_DONE",
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
