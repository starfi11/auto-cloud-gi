import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.adapters.perception import ElementRegistry, ElementResolver


class FakeBackend:
    def __init__(self, text: str = "") -> None:
        self._text = text
        self.locate_calls: list[tuple[str, tuple[int, int, int, int] | None]] = []
        self.clicks: list[tuple[int, int, int]] = []

    def size(self) -> tuple[int, int]:
        return (1600, 900)

    def screenshot(self, region=None):
        return {"text": self._text, "region": region}

    def locate_template(self, template_path, *, confidence=0.9, grayscale=True, region=None):
        self.locate_calls.append((str(template_path), region))
        if region is None:
            return (100, 100, 50, 40)
        # Tests opt-in to ROI hits by toggling locate_roi_hit.
        if getattr(self, "locate_roi_hit", False):
            return (region[0] + 5, region[1] + 5, 50, 40)
        return None

    def click(self, x: int, y: int, clicks: int = 1) -> None:
        self.clicks.append((x, y, clicks))

    def scroll(self, amount: int) -> None:
        return None

    def hotkey(self, *keys: str) -> None:
        return None


class FakeOcr:
    def __init__(self, text: str) -> None:
        self._text = text

    def read_text(self, image):  # noqa: ANN001
        return self._text


class UiElementResolverTest(unittest.TestCase):
    def test_template_first_short_circuits_ocr(self) -> None:
        # Template matchers are cheap (~10ms); OCR is expensive (~800ms).
        # When both are declared, a template hit must skip OCR entirely.
        with TemporaryDirectory() as td:
            td_path = Path(td)
            (td_path / "default").mkdir(parents=True, exist_ok=True)
            (td_path / "default" / "btn.png").write_bytes(b"x")
            spec = {
                "elements": [
                    {
                        "id": "e1",
                        "profile": "default",
                        "roi": [0, 0, 100, 100],
                        "matchers": [
                            {"kind": "text_ocr", "text_any": ["开始游戏"]},
                            {"kind": "template", "template_key": "btn"},
                        ],
                    }
                ]
            }
            spec_path = td_path / "elements.json"
            spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")

            # Make OCR's response irrelevant — if template fires first, OCR
            # should never be consulted. The assertion is that backend.locate
            # ran and r.matcher_kind == "template".
            ocr = FakeOcr("这里有开始游戏按钮")
            ocr_calls: list[int] = []
            original_read = ocr.read_text

            def counted_read(image):  # noqa: ANN001
                ocr_calls.append(1)
                return original_read(image)

            ocr.read_text = counted_read  # type: ignore[assignment]

            backend = FakeBackend(text="这里有开始游戏按钮")
            backend.locate_roi_hit = True  # template matches inside the element's ROI
            registry = ElementRegistry.from_json(str(spec_path))
            resolver = ElementResolver(
                backend,
                registry=registry,
                template_root=str(td_path),
                ocr_engine=ocr,
            )
            r = resolver.resolve(element_id="e1", profile="default", timeout_seconds=0.2, poll_seconds=0.05)
            self.assertTrue(r.ok)
            self.assertEqual(r.matcher_kind, "template")
            self.assertEqual(ocr_calls, [], "OCR must not be called when template hits first")

    def test_roi_miss_falls_back_to_global_template(self) -> None:
        with TemporaryDirectory() as td:
            td_path = Path(td)
            (td_path / "default").mkdir(parents=True, exist_ok=True)
            (td_path / "default" / "btn.png").write_bytes(b"x")
            spec = {
                "elements": [
                    {
                        "id": "e2",
                        "profile": "default",
                        "roi": [10, 10, 100, 60],
                        "matchers": [{"kind": "template", "template_key": "btn"}],
                        "policy": {
                            "timeout_seconds": 0.6,
                            "poll_seconds": 0.05,
                            "roi_fail_to_expand": 1,
                            "expand_fail_to_global": 2,
                        },
                    }
                ]
            }
            spec_path = td_path / "elements.json"
            spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")

            backend = FakeBackend(text="")
            registry = ElementRegistry.from_json(str(spec_path))
            resolver = ElementResolver(
                backend,
                registry=registry,
                template_root=str(td_path),
                ocr_engine=FakeOcr(""),
            )
            r = resolver.resolve(element_id="e2", profile="default")
            self.assertTrue(r.ok)
            self.assertEqual(r.matcher_kind, "template")
            self.assertIsNotNone(r.bbox)
            self.assertTrue(any(region is None for _, region in backend.locate_calls))


if __name__ == "__main__":
    unittest.main()
