import subprocess
import unittest

from src.adapters.runtime.process_registry import ProcessRegistry


class ProcessRegistryTest(unittest.TestCase):
    def test_register_status_terminate(self) -> None:
        reg = ProcessRegistry()
        proc = subprocess.Popen(["sleep", "1"], shell=False)
        reg.register("x", proc)
        status = reg.status("x")
        self.assertTrue(status["exists"])
        self.assertGreater(int(status["pid"]), 0)
        term = reg.terminate("x")
        self.assertTrue(term["ok"])
        proc.wait(timeout=2)


if __name__ == "__main__":
    unittest.main()
