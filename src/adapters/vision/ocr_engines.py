from __future__ import annotations

import os
from typing import Any

from src.ports.ocr_engine_port import OcrEnginePort


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _normalize_paddle_lang(ocr_lang: str) -> str:
    # PaddleOCR language keys are coarse-grained. "ch" covers Chinese + English.
    v = (ocr_lang or "").strip().lower()
    if any(x in v for x in ("chi", "zh", "ch")):
        return "ch"
    if "en" in v:
        return "en"
    return "ch"


class NullOcrEngine(OcrEnginePort):
    def __init__(self) -> None:
        self.last_text = ""

    def read_text(self, image: Any) -> str:
        self.last_text = ""
        return ""


class TesseractOcrEngine(OcrEnginePort):
    def __init__(self, lang: str) -> None:
        self.lang = lang
        self.last_text = ""
        self._cmd = os.getenv("TESSERACT_CMD", "").strip()

    def read_text(self, image: Any) -> str:
        try:
            import pytesseract  # type: ignore

            if self._cmd:
                pytesseract.pytesseract.tesseract_cmd = self._cmd
            text = str(pytesseract.image_to_string(image, lang=self.lang))
            self.last_text = text
            return text
        except Exception as exc:  # noqa: BLE001
            self.last_text = f"<ocr_error:{type(exc).__name__}:{exc}>"
            return ""


class PaddleOcrEngine(OcrEnginePort):
    def __init__(self, lang: str) -> None:
        from paddleocr import PaddleOCR  # type: ignore

        self.last_text = ""
        paddle_lang = _normalize_paddle_lang(lang)
        use_angle_cls = _bool_env("PADDLE_OCR_USE_ANGLE_CLS", default=False)
        show_log = _bool_env("PADDLE_OCR_SHOW_LOG", default=False)
        self._ocr = PaddleOCR(use_angle_cls=use_angle_cls, lang=paddle_lang, show_log=show_log)

    def read_text(self, image: Any) -> str:
        try:
            import numpy as np  # type: ignore

            arr = np.array(image)
            if arr.ndim == 3 and arr.shape[2] >= 3:
                # PIL is RGB, Paddle/OpenCV path prefers BGR.
                arr = arr[:, :, ::-1]
            # result: [ [ [box], (text, score) ], ... ] or nested by page
            result = self._ocr.ocr(arr, cls=False)
            lines: list[str] = []
            if isinstance(result, list):
                for page in result:
                    if not isinstance(page, list):
                        continue
                    for item in page:
                        if not isinstance(item, (list, tuple)) or len(item) < 2:
                            continue
                        rec = item[1]
                        if isinstance(rec, (list, tuple)) and len(rec) >= 1:
                            txt = str(rec[0]).strip()
                            if txt:
                                lines.append(txt)
            text = "\n".join(lines)
            self.last_text = text
            return text
        except Exception as exc:  # noqa: BLE001
            self.last_text = f"<ocr_error:{type(exc).__name__}:{exc}>"
            return ""


def build_ocr_engine() -> OcrEnginePort:
    engine = os.getenv("OCR_ENGINE", "paddle").strip().lower()
    lang = os.getenv("OCR_LANG", "chi_sim+eng")
    strict = _bool_env("OCR_ENGINE_STRICT", default=False)

    if engine == "none":
        return NullOcrEngine()

    if engine == "tesseract":
        return TesseractOcrEngine(lang)

    if engine == "paddle":
        try:
            return PaddleOcrEngine(lang)
        except Exception:
            if strict:
                raise
            return TesseractOcrEngine(lang)

    # Unknown engine: keep runtime alive with a permissive fallback.
    return TesseractOcrEngine(lang)

