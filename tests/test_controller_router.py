import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.adapters.controllers.controller_router import ControllerRouter
from src.domain.workflow import WorkflowStep
from src.infra.log_manager import LogManager
from src.kernel.context_manager import ContextManager
from src.kernel.context_store import RunContext


class FakeController:
    def __init__(self, controller_id: str, prefixes: tuple[str, ...]) -> None:
        self._id = controller_id
        self._prefixes = prefixes
        self.calls: list[str] = []

    @property
    def controller_id(self) -> str:
        return self._id

    def supports(self, step: WorkflowStep) -> bool:
        return any(step.kind.startswith(p) for p in self._prefixes)

    def execute(self, step: WorkflowStep, context: RunContext) -> dict[str, object]:
        self.calls.append(f"{step.name}@{context.active_context_id}")
        return {"ok": True, "controller": self._id}


class ControllerRouterTest(unittest.TestCase):
    def test_router_switches_context_and_selects_controller(self) -> None:
        with TemporaryDirectory() as td:
            logs = LogManager(str(Path(td)))
            router = ControllerRouter(
                controllers=[
                    FakeController("genshin_controller", ("game.",)),
                    FakeController("bettergi_controller", ("assistant.", "system.")),
                ],
                context_manager=ContextManager(default_context_id="global"),
                logs=logs,
            )
            ctx = RunContext(run_id="r1", manifest={}, state="S")

            step = WorkflowStep(
                name="drive_companion",
                kind="assistant.drive",
                params={"required_context": "bettergi_panel", "controller_id": "bettergi_controller"},
            )
            result = router.execute(step, ctx)

            self.assertTrue(result.get("ok"))
            self.assertEqual(result.get("controller"), "bettergi_controller")
            self.assertEqual(ctx.active_context_id, "bettergi_panel")


if __name__ == "__main__":
    unittest.main()
