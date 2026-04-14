from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.adapters.action_specs import launch_macro_update_ignore, one_dragon_drive_macro
from src.adapters.runtime.ui_macro import UiMacroExecutor


@dataclass
class BetterGiDriver:
    macro: UiMacroExecutor

    def dismiss_update_if_present(self, steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        seq = list(steps or launch_macro_update_ignore())
        return self._execute_macro(seq, ok_detail="btgi_update_checked", fail_prefix="btgi_update_check_failed")

    def configure_and_start_one_dragon(self, steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        seq = list(steps or one_dragon_drive_macro())
        return self._execute_macro(seq, ok_detail="btgi_drive_actions_done", fail_prefix="btgi_drive_actions_failed")

    def _execute_macro(self, steps: list[dict[str, Any]], *, ok_detail: str, fail_prefix: str) -> dict[str, Any]:
        results = self.macro.execute(steps)
        failed = [r for r in results if not r.ok]
        return {
            "ok": len(failed) == 0,
            "retryable": True if failed else False,
            "detail": ok_detail if not failed else f"{fail_prefix}:{len(failed)}",
            "macro_results": [r.__dict__ for r in results],
        }
