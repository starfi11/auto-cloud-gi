import unittest

from src.adapters.runtime.ui_macro import NoopUiBackend, UiMacroExecutor


class UiMacroTest(unittest.TestCase):
    def test_execute_macro_steps(self) -> None:
        ex = UiMacroExecutor(NoopUiBackend(width=1600, height=900))
        results = ex.execute(
            [
                {"op": "click", "x": 800, "y": 450, "base_w": 1600, "base_h": 900},
                {"op": "hotkey", "keys": ["alt", "tab"]},
                {"op": "scroll", "amount": -200},
            ]
        )
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r.ok for r in results))


if __name__ == "__main__":
    unittest.main()
