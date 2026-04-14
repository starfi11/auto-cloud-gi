from __future__ import annotations

from typing import Any


def cloud_queue_macro(strategy: str) -> list[dict[str, Any]]:
    points: dict[str, tuple[int, int]] = {
        "claim_gift": (912, 813),
        "start_game": (1395, 813),
        "queue_normal": (959, 642),
        "queue_quick": (872, 477),
    }
    steps: list[dict[str, Any]] = [
        {
            "op": "click",
            "x": points["claim_gift"][0],
            "y": points["claim_gift"][1],
            "base_w": 1600,
            "base_h": 900,
            "after_sleep": 2.0,
        },
        {
            "op": "click",
            "x": points["claim_gift"][0],
            "y": points["claim_gift"][1],
            "base_w": 1600,
            "base_h": 900,
            "after_sleep": 2.0,
        },
        {
            "op": "click",
            "x": points["start_game"][0],
            "y": points["start_game"][1],
            "base_w": 1600,
            "base_h": 900,
            "after_sleep": 3.0,
        },
    ]
    s = strategy.strip().lower()
    if s == "quick":
        steps.append(
            {
                "op": "click",
                "x": points["queue_quick"][0],
                "y": points["queue_quick"][1],
                "base_w": 1600,
                "base_h": 900,
                "after_sleep": 1.0,
            }
        )
    elif s != "none":
        steps.append(
            {
                "op": "click",
                "x": points["queue_normal"][0],
                "y": points["queue_normal"][1],
                "base_w": 1600,
                "base_h": 900,
                "after_sleep": 1.0,
            }
        )
    return steps


def post_ready_macro() -> list[dict[str, Any]]:
    return [
        {"op": "click", "x": 960, "y": 975, "base_w": 1600, "base_h": 900, "after_sleep": 40.0},
        {"op": "click", "x": 1539, "y": 981, "base_w": 1600, "base_h": 900, "clicks": 2, "after_sleep": 3.0},
        {"op": "click", "x": 1539, "y": 981, "base_w": 1600, "base_h": 900, "clicks": 2, "after_sleep": 3.0},
        {"op": "click", "x": 1676, "y": 1009, "base_w": 1600, "base_h": 900, "clicks": 2, "after_sleep": 5.0},
        {"op": "click", "x": 1676, "y": 1009, "base_w": 1600, "base_h": 900, "clicks": 2, "after_sleep": 5.0},
        {"op": "click", "x": 1538, "y": 1472, "base_w": 1600, "base_h": 900, "clicks": 2, "after_sleep": 1.0},
    ]
