import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.adapters.policy import TablePolicyEngine
from src.adapters.state import ContextStateEstimator
from src.app.run_executor import RunExecutor
from src.domain.state_kernel import StateEstimate
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


class AcceptableTargetEstimator:
    def estimate(self, context, plan, expected_states=None):
        if expected_states and "S_C" in expected_states:
            return StateEstimate(state="S_C", confidence=1.0, signals={"source": "test"}, uncertainty_reason="")
        state = context.state
        if not state and plan.state_plan is not None:
            state = plan.state_plan.initial_state
        return StateEstimate(state=state or "BOOTSTRAP", confidence=1.0, signals={"source": "test"}, uncertainty_reason="")


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

    def test_pending_transition_accepts_alternative_expected_target(self) -> None:
        with TemporaryDirectory() as td:
            runtime_dir = Path(td)
            logs = LogManager(str(runtime_dir))
            checkpoints = CheckpointStore(str(runtime_dir))
            runtime = FakeRuntime()

            executor = RunExecutor(
                logs=logs,
                checkpoints=checkpoints,
                runtime=runtime,
                state_estimator=AcceptableTargetEstimator(),
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
                            action=ActionIntent(
                                name="a",
                                kind="game.launch",
                                params={
                                    "transition_settle_seconds": 0.0,
                                    "transition_timeout_seconds": 3.0,
                                    "transition_require_observed": True,
                                    "transition_observed_ticks": 1,
                                    "transition_observe_interval_seconds": 1.1,
                                },
                            ),
                            next_state="S_B",
                            expected_next=("S_B", "S_C"),
                        ),
                        StateNode(
                            state="S_B",
                            recognition={"profile": "test", "expr": {"present": "never_hit"}},
                            next_state="S_DONE",
                        ),
                        StateNode(
                            state="S_C",
                            action=ActionIntent(name="c", kind="assistant.drive"),
                            next_state="S_DONE",
                        ),
                    ],
                ),
                steps=[],
            )
            ctx = RunContext(run_id="r-state-alt", manifest={"run_id": "r-state-alt"}, state="BOOTSTRAP")
            executor.execute(ctx, plan)

            self.assertEqual(runtime.calls, ["a", "c"])
            self.assertEqual(ctx.state, "FINISH")


if __name__ == "__main__":
    unittest.main()
