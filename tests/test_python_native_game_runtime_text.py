import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep

from src.adapters.runtime.python_native_game_runtime import PythonNativeGameRuntimeAdapter


class PythonNativeGameRuntimeTextTest(unittest.TestCase):
    def test_wait_scene_ready_by_text_signal(self) -> None:
        with TemporaryDirectory() as td:
            signal = Path(td) / "latest.txt"
            signal.write_text("loading", encoding="utf-8")

            def writer() -> None:
                sleep(0.1)
                signal.write_text("点击进入", encoding="utf-8")

            threading.Thread(target=writer, daemon=True).start()

            rt = PythonNativeGameRuntimeAdapter()
            r = rt.wait_scene_ready(
                {
                    "timeout_seconds": 2.0,
                    "scene_ready_text_any": ["点击进入"],
                    "scene_block_text_any": ["网络较差"],
                    "text_signal_file": str(signal),
                    "text_poll_seconds": 0.05,
                }
            )
            self.assertTrue(r.get("ok"))
            self.assertEqual(r.get("detail"), "scene_ready_by_text_signal")


if __name__ == "__main__":
    unittest.main()
