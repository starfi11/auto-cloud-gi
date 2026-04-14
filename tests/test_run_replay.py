import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.infra.log_manager import LogManager
from src.infra.run_replay import load_run_timeline, replay_state_transitions


class RunReplayTest(unittest.TestCase):
    def test_timeline_is_ordered_by_seq(self) -> None:
        with TemporaryDirectory() as td:
            logs = LogManager(td)
            run_id = "r-seq"
            logs.run_event(run_id, "a", {"x": 1})
            logs.action_event(run_id, "act", "started", {"a": 1})
            logs.state_transition(run_id, "S1", "S2", reason="test")
            logs.replay_event(run_id, "transition", {"from": "S1", "to": "S2", "reason": "test"})
            logs.replay_event(run_id, "transition", {"from": "S2", "to": "S3", "reason": "test2"})

            timeline = load_run_timeline(td, run_id)
            self.assertGreaterEqual(len(timeline), 3)
            seqs = [int(ev.get("seq", 0)) for ev in timeline]
            self.assertEqual(seqs, sorted(seqs))
            self.assertTrue(all(s > 0 for s in seqs))
            replay = replay_state_transitions(td, run_id)
            self.assertTrue(replay.ok)
            self.assertEqual(replay.replayed_final_state, "S3")


if __name__ == "__main__":
    unittest.main()
