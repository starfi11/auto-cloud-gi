import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.app.run_executor import RunExecutor
from src.domain.workflow import WorkflowPlan, WorkflowStep
from src.kernel.checkpoint_store import CheckpointStore
from src.kernel.context_store import RunContext
from src.infra.log_manager import LogManager


class FakeRuntime:
    def __init__(self, handler):
        self._handler = handler

    def execute(self, step: WorkflowStep, context: RunContext) -> dict[str, object]:
        return self._handler(step, context)


class RunExecutorTest(unittest.TestCase):
    def test_step_retries_then_succeeds(self) -> None:
        with TemporaryDirectory() as td:
            runtime_dir = Path(td)
            logs = LogManager(str(runtime_dir))
            checkpoints = CheckpointStore(str(runtime_dir))

            call_count = {"n": 0}

            def flaky_handler(step: WorkflowStep, _ctx: RunContext) -> dict[str, object]:
                call_count["n"] += 1
                if call_count["n"] < 3:
                    return {"ok": False, "retryable": True, "detail": "temp_fail"}
                return {"ok": True, "detail": "ok_after_retry"}

            runtime = FakeRuntime(flaky_handler)
            executor = RunExecutor(logs=logs, checkpoints=checkpoints, runtime=runtime)
            ctx = RunContext(run_id="r1", manifest={"run_id": "r1"}, state="BOOTSTRAP")
            plan = WorkflowPlan(
                profile="test",
                game="test",
                scenario="test",
                steps=[
                    WorkflowStep(
                        name="drive",
                        kind="assistant.drive",
                        params={"max_retries": 2, "backoff_seconds": 0.01},
                    )
                ],
            )

            executor.execute(ctx, plan)
            self.assertEqual(call_count["n"], 3)
            self.assertEqual(ctx.state, "FINISH")


if __name__ == "__main__":
    unittest.main()
