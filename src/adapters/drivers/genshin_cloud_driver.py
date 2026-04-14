from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.adapters.action_specs import cloud_queue_macro, kongyue_claim_macro, post_ready_macro
from src.adapters.runtime.ui_macro import UiMacroExecutor


@dataclass
class GenshinCloudDriver:
    macro: UiMacroExecutor

    def enter_queue(self, strategy: str, extra_steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        steps = list(extra_steps or cloud_queue_macro(strategy))
        return self._execute_macro(steps, ok_detail="queue_actions_done", fail_prefix="queue_actions_failed")

    def settle_after_enter_game(self, steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        seq = list(steps or post_ready_macro())
        return self._execute_macro(seq, ok_detail="post_enter_actions_done", fail_prefix="post_enter_actions_failed")

    def claim_kongyue(self, steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        seq = list(steps or kongyue_claim_macro())
        return self._execute_macro(seq, ok_detail="kongyue_claim_done", fail_prefix="kongyue_claim_failed")

    def _execute_macro(self, steps: list[dict[str, Any]], *, ok_detail: str, fail_prefix: str) -> dict[str, Any]:
        results = self.macro.execute(steps)
        failed = [r for r in results if not r.ok]
        return {
            "ok": len(failed) == 0,
            "retryable": True if failed else False,
            "detail": ok_detail if not failed else f"{fail_prefix}:{len(failed)}",
            "macro_results": [r.__dict__ for r in results],
        }
