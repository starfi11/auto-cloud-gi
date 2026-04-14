import unittest

from src.adapters.runtime import NoopAssistantRuntimeAdapter, NoopGameRuntimeAdapter
from src.app.action_dispatcher import ActionDispatcher
from src.domain.actions import WaitGameReadyAction
from src.domain.workflow import WorkflowStep
from src.kernel.context_store import RunContext


class ActionDispatcherTest(unittest.TestCase):
    def test_dispatcher_builds_action_subclass(self) -> None:
        dispatcher = ActionDispatcher(
            game_runtime=NoopGameRuntimeAdapter(),
            assistant_runtime=NoopAssistantRuntimeAdapter(),
        )
        ctx = RunContext(run_id="r1", manifest={}, state="BOOTSTRAP")
        step = WorkflowStep(name="wait", kind="game.wait.scene", params={})
        action = dispatcher.create_action(step, ctx)
        self.assertIsInstance(action, WaitGameReadyAction)

    def test_dispatcher_executes_action(self) -> None:
        dispatcher = ActionDispatcher(
            game_runtime=NoopGameRuntimeAdapter(),
            assistant_runtime=NoopAssistantRuntimeAdapter(),
        )
        ctx = RunContext(run_id="r2", manifest={}, state="BOOTSTRAP")
        step = WorkflowStep(name="launch", kind="game.launch", params={})
        result = dispatcher.execute(step, ctx)
        self.assertTrue(result.get("ok"))


if __name__ == "__main__":
    unittest.main()
