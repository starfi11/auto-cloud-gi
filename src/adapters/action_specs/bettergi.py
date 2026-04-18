from __future__ import annotations

from typing import Any


def launch_macro_update_ignore() -> list[dict[str, Any]]:
    return [
        {
            "op": "click_element",
            "element_id": "btgi_update_ignore_button",
            "element_profile": "bettergi",
            "timeout_seconds": 2.5,
            "poll_seconds": 0.2,
            "optional": True,
            "after_sleep": 0.4,
        }
    ]


def one_dragon_drive_macro() -> list[dict[str, Any]]:
    # Migrated from v2 ahk/change_btgi_window.ahk
    return [
        {
            "op": "click_element",
            "element_id": "btgi_screenshot_dropdown_settings",
            "element_profile": "bettergi",
            "timeout_seconds": 12.0,
            "poll_seconds": 0.25,
            "after_sleep": 0.3,
        },
        {"op": "hotkey", "keys": ["end"], "after_sleep": 0.1},
        {"op": "hotkey", "keys": ["ctrl", "end"], "after_sleep": 0.1},
        {"op": "scroll", "amount": -600, "after_sleep": 0.2},
        {
            "op": "click_element",
            "element_id": "btgi_dropdown_arrow",
            "element_profile": "bettergi",
            "timeout_seconds": 10.0,
            "poll_seconds": 0.25,
            "after_sleep": 0.5,
        },
        {"op": "hotkey", "keys": ["enter"], "after_sleep": 0.4},
        {"op": "hotkey", "keys": ["alt", "tab"], "after_sleep": 0.8},
        {
            "op": "click_element",
            "element_id": "btgi_one_click_start_button",
            "element_profile": "bettergi",
            "timeout_seconds": 12.0,
            "poll_seconds": 0.25,
            "after_sleep": 0.4,
        },
    ]
