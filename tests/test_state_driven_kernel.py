import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.adapters.policy import TablePolicyEngine
from src.adapters.state import ContextStateEstimator
from src.app.run_executor import RunExecutor
from src.domain.workflow import ActionIntent, StateNode, StatePlan, WorkflowPlan
from src.infra.log_manager import LogManager
from src.kernel.checkpoint_store import CheckpointStore
from src.kernel.context_store import RunContext


class FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, step, context):
        self.calls.append(step.name)
        return {"ok": True, "state": context.state}


class StateDrivenKernelTest(unittest.TestCase):
    def test_state_driven_loop_executes_actions_and_finishes(self) -> None:
        with TemporaryDirectory() as td:
            runtime_dir = Path(td)
            logs = LogManager(str(runtime_dir))
            checkpoints = CheckpointStore(str(runtime_dir))
            runtime = FakeRuntime()

            executor = RunExecutor(
                logs=logs,
                checkpoints=checkpoints,
                runtime=runtime,
                state_estimator=ContextStateEstimator(),
                policy_engine=TablePolicyEngine(),
            )
            plan = WorkflowPlan(
                profile="test",
                game="test",
                scenario="test",
                mode="state_driven",
                state_plan=StatePlan(
                    initial_state="S_A",
                    terminal_states=["S_DONE"],
                    max_ticks=20,
                    nodes=[
                        StateNode(
                            state="S_A",
                            action=ActionIntent(name="a", kind="game.launch"),
                            next_state="S_B",
                        ),
                        StateNode(
                            state="S_B",
                            action=ActionIntent(name="b", kind="assistant.drive"),
                            next_state="S_DONE",
                        ),
                    ],
                ),
                steps=[],
            )
            ctx = RunContext(run_id="r-state", manifest={"run_id": "r-state"}, state="BOOTSTRAP")
            executor.execute(ctx, plan)

            self.assertEqual(runtime.calls, ["a", "b"])
            self.assertEqual(ctx.state, "FINISH")
            self.assertEqual(ctx.layered_state.global_layer.state, "FINISH")


if __name__ == "__main__":
    unittest.main()
