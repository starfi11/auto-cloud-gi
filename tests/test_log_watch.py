import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep

from src.adapters.runtime.log_watch import LogActivityWatcher, LogWatchSpec


class LogWatchTest(unittest.TestCase):
    def test_wait_until_idle_after_activity(self) -> None:
        with TemporaryDirectory() as td:
            log_dir = Path(td)
            p = log_dir / "x.log"
            p.write_text("a\n", encoding="utf-8")

            def writer() -> None:
                sleep(0.1)
                p.write_text("a\nb\n", encoding="utf-8")

            t = threading.Thread(target=writer, daemon=True)
            t.start()

            watcher = LogActivityWatcher()
            r = watcher.wait_until_idle(
                LogWatchSpec(
                    root=str(log_dir),
                    glob="*.log",
                    idle_seconds=0.2,
                    timeout_seconds=2.0,
                    poll_interval_seconds=0.05,
                    require_activity=True,
                )
            )
            self.assertTrue(r.ok)
            self.assertIn("log_idle_reached", r.detail)
            self.assertGreaterEqual(r.changed_count, 1)


if __name__ == "__main__":
    unittest.main()
