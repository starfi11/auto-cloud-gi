import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep

from src.adapters.vision import FileTextSignalSource, TextSignalWaiter, TextWaitSpec


class TextSignalTest(unittest.TestCase):
    def test_wait_until_ready(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "latest.txt"
            p.write_text("loading", encoding="utf-8")

            def writer() -> None:
                sleep(0.1)
                p.write_text("已进入 点击进入", encoding="utf-8")

            threading.Thread(target=writer, daemon=True).start()
            r = TextSignalWaiter().wait_until_ready(
                FileTextSignalSource(str(p)),
                TextWaitSpec(ready_any=["点击进入"], block_any=["网络较差"], timeout_seconds=2.0, poll_seconds=0.05),
            )
            self.assertTrue(r.ok)
            self.assertEqual(r.matched_ready, "点击进入")


if __name__ == "__main__":
    unittest.main()
