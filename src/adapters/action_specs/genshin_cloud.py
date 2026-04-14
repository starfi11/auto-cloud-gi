from __future__ import annotations

from typing import Any


def cloud_queue_macro(strategy: str) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [
        {
            "op": "click_element",
            "element_id": "cloud_claim_gift_close",
            "element_profile": "genshin_cloud",
            "timeout_seconds": 6.0,
            "poll_seconds": 0.25,
            "optional": True,
            "after_sleep": 0.5,
        },
        {
            "op": "click_element",
            "element_id": "cloud_start_game_button",
            "element_profile": "genshin_cloud",
            "timeout_seconds": 12.0,
            "poll_seconds": 0.25,
            "after_sleep": 0.8,
        },
    ]
    s = strategy.strip().lower()
    if s == "quick":
        steps.append(
            {
                "op": "click_element",
                "element_id": "cloud_queue_quick_button",
                "element_profile": "genshin_cloud",
                "timeout_seconds": 8.0,
                "poll_seconds": 0.25,
                "after_sleep": 0.6,
            }
        )
    elif s != "none":
        steps.append(
            {
                "op": "click_element",
                "element_id": "cloud_queue_normal_button",
                "element_profile": "genshin_cloud",
                "timeout_seconds": 8.0,
                "poll_seconds": 0.25,
                "after_sleep": 0.6,
            }
        )
    return steps


def post_ready_macro() -> list[dict[str, Any]]:
    # Reserved for future in-game follow-up actions.
    return []


def kongyue_claim_macro() -> list[dict[str, Any]]:
    # Sequence: double click -> wait 2s -> single click, repeat once.
    base = {
        "op": "click_element",
        "element_id": "cloud_kongyue_reward_text",
        "element_profile": "genshin_cloud",
        "timeout_seconds": 2.0,
        "poll_seconds": 0.08,
    }
    return [
        {**base, "clicks": 2, "after_sleep": 2.0},
        {**base, "clicks": 1, "after_sleep": 0.4},
        {**base, "clicks": 2, "after_sleep": 2.0},
        {**base, "clicks": 1, "after_sleep": 0.4},
    ]
