from src.adapters.action_specs.bettergi import (
    adjust_capture_and_open_one_dragon_macro,
    launch_macro_update_ignore,
    one_dragon_drive_macro,
    prepare_capture_dropdown_macro,
    start_one_dragon_macro,
)
from src.adapters.action_specs.genshin_cloud import cloud_queue_macro, kongyue_claim_macro, post_ready_macro
from src.adapters.action_specs.genshin_pc import pc_skip_queue_macro

__all__ = [
    "cloud_queue_macro",
    "post_ready_macro",
    "kongyue_claim_macro",
    "launch_macro_update_ignore",
    "one_dragon_drive_macro",
    "prepare_capture_dropdown_macro",
    "adjust_capture_and_open_one_dragon_macro",
    "start_one_dragon_macro",
    "pc_skip_queue_macro",
]
