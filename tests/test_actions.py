import unittest

from src.domain.actions import DriveAssistantAction
from src.domain.workflow import WorkflowStep
from src.kernel.context_store import RunContext


class FakeAssistant:
    def __init__(self) -> None:
        self.calls = []

    def launch(self, options):
        return {"ok": True}

    def drive(self, scenario, options):
        self.calls.append((scenario, options))
        return {"ok": True}

    def collect(self, options):
        return {"ok": True}

    def stop(self):
        return {"ok": True}


class ActionsTest(unittest.TestCase):
    def test_action_injects_context_meta(self) -> None:
        step = WorkflowStep(name="drive", kind="assistant.drive", params={"scenario": "daily"})
        assistant = FakeAssistant()
        action = DriveAssistantAction(step=step, assistant_runtime=assistant)
        ctx = RunContext(run_id="r123", manifest={}, state="MONITOR_AND_GUARD")
        result = action.execute(ctx)
        self.assertTrue(result["ok"])
        self.assertEqual(len(assistant.calls), 1)
        scenario, options = assistant.calls[0]
        self.assertEqual(scenario, "daily")
        self.assertEqual(options["run_id"], "r123")
        self.assertEqual(options["state"], "MONITOR_AND_GUARD")


if __name__ == "__main__":
    unittest.main()
