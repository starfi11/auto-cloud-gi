import unittest

from src.adapters.recovery import TableRecoveryStrategy
from src.domain.workflow import WorkflowStep
from src.kernel.context_store import RunContext


class RecoveryStrategyTest(unittest.TestCase):
    def test_focus_lost_maps_to_context_switch_retry(self) -> None:
        strategy = TableRecoveryStrategy()
        step = WorkflowStep(
            name="drive",
            kind="assistant.drive",
            params={"required_context": "bettergi_panel"},
        )
        ctx = RunContext(run_id="r", manifest={}, state="S")
        directive = strategy.plan(
            step=step,
            context=ctx,
            result={"ok": False, "retryable": True, "detail": "window_not_foreground"},
            attempt=1,
            max_retries=0,
        )
        self.assertEqual(directive.decision, "switch_context_then_retry")
        self.assertEqual(directive.target_context_id, "bettergi_panel")


if __name__ == "__main__":
    unittest.main()
