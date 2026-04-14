import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.infra.log_manager import LogManager


class LogManagerTest(unittest.TestCase):
    def test_run_logs_are_written(self) -> None:
        with TemporaryDirectory() as td:
            logs = LogManager(td)
            run_id = "run-1"
            logs.system_event("boot", {"a": 1})
            logs.control_api_event("request", {"path": "/api/v1/runs"})
            logs.run_event(run_id, "RUN.ACCEPTED", {"trigger": "API_TRIGGER"})
            logs.state_transition(run_id, "BOOTSTRAP", "LOAD_POLICY", reason="policy_loaded")
            logs.action_event(run_id, "start_cloud_gi", "ok", {"elapsed_ms": 123})
            logs.replay_event(run_id, "transition", {"from": "BOOTSTRAP", "to": "LOAD_POLICY"})
            summary_path = logs.write_run_summary(run_id, {"status": "accepted"})

            self.assertTrue((Path(td) / "logs" / "system.jsonl").exists())
            self.assertTrue((Path(td) / "logs" / "control_api.jsonl").exists())
            self.assertTrue((Path(td) / "logs" / "runs" / run_id / "events.jsonl").exists())
            self.assertTrue((Path(td) / "logs" / "runs" / run_id / "state_transitions.jsonl").exists())
            self.assertTrue((Path(td) / "logs" / "runs" / run_id / "actions.jsonl").exists())
            self.assertTrue((Path(td) / "logs" / "runs" / run_id / "replay_trace.jsonl").exists())
            self.assertTrue(summary_path.exists())

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "accepted")


if __name__ == "__main__":
    unittest.main()
