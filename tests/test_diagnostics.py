import unittest

from src.infra.diagnostics import classify_failure


class DiagnosticsTest(unittest.TestCase):
    def test_classify_path_not_found(self) -> None:
        d = classify_failure("game_launch_failed:[WinError 2]")
        self.assertEqual(d.code, "PATH_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
