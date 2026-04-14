from __future__ import annotations

from typing import Any


def launch_macro_update_ignore() -> list[dict[str, Any]]:
    return [{"op": "click", "x": 1133, "y": 825, "base_w": 1600, "base_h": 900, "after_sleep": 0.8}]


def one_dragon_drive_macro() -> list[dict[str, Any]]:
    # Migrated from v2 ahk/change_btgi_window.ahk
    return [
        {"op": "click", "x": 1345, "y": 527, "base_w": 1600, "base_h": 900, "after_sleep": 0.4},
        {"op": "hotkey", "keys": ["end"], "after_sleep": 0.1},
        {"op": "hotkey", "keys": ["ctrl", "end"], "after_sleep": 0.1},
        {"op": "scroll", "amount": -600, "after_sleep": 0.2},
        {"op": "click", "x": 1263, "y": 587, "base_w": 1600, "base_h": 900, "after_sleep": 0.4},
        {"op": "click", "x": 716, "y": 447, "base_w": 1600, "base_h": 900, "clicks": 2, "after_sleep": 1.0},
        {"op": "hotkey", "keys": ["alt", "tab"], "after_sleep": 0.8},
        {"op": "click", "x": 579, "y": 443, "base_w": 1600, "base_h": 900, "after_sleep": 0.4},
        {"op": "click", "x": 855, "y": 295, "base_w": 1600, "base_h": 900, "after_sleep": 0.4},
    ]
