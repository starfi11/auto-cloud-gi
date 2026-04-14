import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.adapters.vision import TemplateStore


class TemplateStoreTest(unittest.TestCase):
    def test_resolve_scoped_template(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            p = root / "genshin_cloud_bettergi" / "start_button.png"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x", encoding="utf-8")

            ref = TemplateStore(str(root)).resolve("start_button", profile="genshin_cloud_bettergi")
            self.assertTrue(ref.path.endswith("start_button.png"))


if __name__ == "__main__":
    unittest.main()
