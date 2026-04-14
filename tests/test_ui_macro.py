import unittest
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

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

    def test_click_element_op(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "default").mkdir(parents=True, exist_ok=True)
            (root / "default" / "btn.png").write_bytes(b"x")
            spec = {
                "elements": [
                    {
                        "id": "btn",
                        "profile": "default",
                        "matchers": [{"kind": "template", "template_key": "btn"}],
                    }
                ]
            }
            spec_path = root / "elements.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            old_spec = os.environ.get("VISION_ELEMENT_SPEC")
            old_root = os.environ.get("VISION_TEMPLATE_ROOT")
            os.environ["VISION_ELEMENT_SPEC"] = str(spec_path)
            os.environ["VISION_TEMPLATE_ROOT"] = str(root)
            try:
                ex = UiMacroExecutor(NoopUiBackend(width=1600, height=900))
                results = ex.execute(
                    [
                        {
                            "op": "click_element",
                            "element_id": "btn",
                            "element_profile": "default",
                            "timeout_seconds": 0.2,
                            "poll_seconds": 0.05,
                            "optional": True,
                        }
                    ]
                )
                self.assertEqual(len(results), 1)
                self.assertTrue(results[0].ok)
            finally:
                if old_spec is None:
                    os.environ.pop("VISION_ELEMENT_SPEC", None)
                else:
                    os.environ["VISION_ELEMENT_SPEC"] = old_spec
                if old_root is None:
                    os.environ.pop("VISION_TEMPLATE_ROOT", None)
                else:
                    os.environ["VISION_TEMPLATE_ROOT"] = old_root


if __name__ == "__main__":
    unittest.main()
