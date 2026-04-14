import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from src.adapters.runtime import NoopAssistantRuntimeAdapter, NoopGameRuntimeAdapter
from src.app.orchestrator import Orchestrator
from src.domain.run_request import RunRequest


class OrchestratorTest(unittest.TestCase):
    def test_idempotent_start_run(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            runtime_dir = tmp / "runtime"
            command_file = tmp / "commands.json"
            command_file.write_text('{"overrides": {"x": 1}}', encoding="utf-8")

            orch = Orchestrator(
                runtime_dir=str(runtime_dir),
                command_source_file=str(command_file),
                game_runtime=NoopGameRuntimeAdapter(),
                assistant_runtime=NoopAssistantRuntimeAdapter(),
            )

            req = RunRequest(trigger="API_TRIGGER", idempotency_key="k1")
            r1 = orch.start_run(req)
            r2 = orch.start_run(req)
            orch.wait_run(r1.run_id, timeout_seconds=1)

            self.assertTrue(r1.accepted)
            self.assertTrue(r2.accepted)
            self.assertEqual(r1.run_id, r2.run_id)

    def test_manifest_contains_profile_and_workflow(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            runtime_dir = tmp / "runtime"
            command_file = tmp / "commands.json"
            command_file.write_text('{"overrides": {"x": 1}}', encoding="utf-8")

            orch = Orchestrator(
                runtime_dir=str(runtime_dir),
                command_source_file=str(command_file),
                game_runtime=NoopGameRuntimeAdapter(),
                assistant_runtime=NoopAssistantRuntimeAdapter(),
            )

            req = RunRequest(
                trigger="API_TRIGGER",
                idempotency_key="k2",
                target_profile="genshin_cloud_bettergi",
                scenario="daily_commission_only",
            )
            receipt = orch.start_run(req)
            self.assertTrue(receipt.accepted)
            orch.wait_run(receipt.run_id, timeout_seconds=1)

            manifest_path = runtime_dir / "manifests" / f"{receipt.run_id}.json"
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["target_profile"], "genshin_cloud_bettergi")
            self.assertEqual(manifest["scenario"], "daily_commission_only")
            self.assertIn("workflow_plan", manifest)
            self.assertGreater(len(manifest["workflow_plan"]["steps"]), 0)

    def test_unknown_profile_raises(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            runtime_dir = tmp / "runtime"
            command_file = tmp / "commands.json"
            command_file.write_text("{}", encoding="utf-8")
            orch = Orchestrator(
                runtime_dir=str(runtime_dir),
                command_source_file=str(command_file),
                game_runtime=NoopGameRuntimeAdapter(),
                assistant_runtime=NoopAssistantRuntimeAdapter(),
            )

            with self.assertRaises(ValueError):
                orch.start_run(
                    RunRequest(
                        trigger="API_TRIGGER",
                        idempotency_key="k-unknown",
                        target_profile="unknown_profile",
                        scenario="default",
                    )
                )

    def test_idempotency_persisted_after_restart(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            runtime_dir = tmp / "runtime"
            command_file = tmp / "commands.json"
            command_file.write_text("{}", encoding="utf-8")

            orch1 = Orchestrator(
                runtime_dir=str(runtime_dir),
                command_source_file=str(command_file),
                game_runtime=NoopGameRuntimeAdapter(),
                assistant_runtime=NoopAssistantRuntimeAdapter(),
            )
            req = RunRequest(trigger="API_TRIGGER", idempotency_key="persist-k")
            r1 = orch1.start_run(req)
            self.assertTrue(r1.accepted)
            orch1.wait_run(r1.run_id, timeout_seconds=1)

            orch2 = Orchestrator(
                runtime_dir=str(runtime_dir),
                command_source_file=str(command_file),
                game_runtime=NoopGameRuntimeAdapter(),
                assistant_runtime=NoopAssistantRuntimeAdapter(),
            )
            r2 = orch2.start_run(req)
            self.assertTrue(r2.accepted)
            self.assertEqual(r1.run_id, r2.run_id)
            self.assertEqual(r2.reason, "idempotent_reuse")

    def test_interrupt_run(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            runtime_dir = tmp / "runtime"
            command_file = tmp / "commands.json"
            command_file.write_text("{}", encoding="utf-8")
            orch = Orchestrator(
                runtime_dir=str(runtime_dir),
                command_source_file=str(command_file),
                game_runtime=NoopGameRuntimeAdapter(),
                assistant_runtime=NoopAssistantRuntimeAdapter(),
            )

            req = RunRequest(
                trigger="API_TRIGGER",
                idempotency_key="k-interrupt",
                target_profile="genshin_cloud_bettergi",
                scenario="debug_slow_wait",
            )
            receipt = orch.start_run(req)
            self.assertTrue(receipt.accepted)
            self.assertTrue(orch.interrupt_run(receipt.run_id, "unit_test_interrupt"))
            self.assertTrue(orch.wait_run(receipt.run_id, timeout_seconds=2))
            run = orch.get_run(receipt.run_id)
            self.assertIsNotNone(run)
            self.assertEqual(run.status, "interrupted")


if __name__ == "__main__":
    unittest.main()
