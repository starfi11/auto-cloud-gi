import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.adapters.runtime import NoopAssistantRuntimeAdapter, NoopGameRuntimeAdapter
from src.app.orchestrator import Orchestrator
from src.app.profile_registry import UnknownProfileError
from src.domain.run_request import RunRequest


class OrchestratorProfilesTest(unittest.TestCase):
    def test_rejects_unregistered_profile(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            runtime_dir = tmp / "runtime"
            cmd_file = tmp / "commands.json"
            cmd_file.write_text("{}", encoding="utf-8")
            orch = Orchestrator(
                runtime_dir=str(runtime_dir),
                command_source_file=str(cmd_file),
                game_runtime=NoopGameRuntimeAdapter(),
                assistant_runtime=NoopAssistantRuntimeAdapter(),
            )
            with self.assertRaises(UnknownProfileError):
                orch.start_run(
                    RunRequest(
                        trigger="API_TRIGGER",
                        idempotency_key="pc-1",
                        target_profile="genshin_pc_bettergi",
                        scenario="daily_default",
                    )
                )


if __name__ == "__main__":
    unittest.main()
