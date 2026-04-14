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


class PaddleOcrEngine(OcrEnginePort):
    def __init__(self, lang: str) -> None:
        # Keep runtime conservative on Windows CPU to avoid PIR-related kernel issues.
        os.environ["FLAGS_enable_pir_api"] = os.getenv("PADDLE_FLAGS_ENABLE_PIR_API", "0").strip() or "0"
        from paddleocr import PaddleOCR  # type: ignore

        self.last_text = ""
        paddle_lang = _normalize_paddle_lang(lang)
        ocr_version = os.getenv("PADDLE_OCR_VERSION", "PP-OCRv5").strip() or "PP-OCRv5"
        use_doc_orientation_classify = _bool_env("PADDLE_OCR_USE_DOC_ORIENTATION", default=False)
        use_doc_unwarping = _bool_env("PADDLE_OCR_USE_DOC_UNWARPING", default=False)
        use_textline_orientation = _bool_env("PADDLE_OCR_USE_TEXTLINE_ORI", default=False)
        # Fixed runtime contract: PaddleOCR 3.x style init.
        self._ocr = PaddleOCR(
            lang=paddle_lang,
            ocr_version=ocr_version,
            use_doc_orientation_classify=use_doc_orientation_classify,
            use_doc_unwarping=use_doc_unwarping,
            use_textline_orientation=use_textline_orientation,
        )
        print(
            "[ocr] paddle init "
            f"lang={paddle_lang} ocr_version={ocr_version} "
            f"doc_ori={use_doc_orientation_classify} doc_unwarp={use_doc_unwarping} "
            f"textline_ori={use_textline_orientation} FLAGS_enable_pir_api={os.getenv('FLAGS_enable_pir_api','')}",
            flush=True,
        )

    def read_text(self, image: Any) -> str:
        try:
            import numpy as np  # type: ignore

            arr = np.array(image)
            if arr.ndim == 3 and arr.shape[2] >= 3:
                # PIL is RGB, Paddle/OpenCV path prefers BGR.
                arr = arr[:, :, ::-1]
            # Fixed runtime contract: PaddleOCR 3.x style inference.
            result = self._ocr.predict(arr)
            lines: list[str] = []
            if isinstance(result, list):
                for page in result:
                    if isinstance(page, dict):
                        rec_texts = page.get("rec_texts")
                        if isinstance(rec_texts, list):
                            lines.extend([str(x).strip() for x in rec_texts if str(x).strip()])
                        continue
                    rec_texts = getattr(page, "rec_texts", None)
                    if isinstance(rec_texts, list):
                        lines.extend([str(x).strip() for x in rec_texts if str(x).strip()])
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

    if engine == "paddle":
        try:
            return PaddleOcrEngine(lang)
        except Exception as exc:
            if strict:
                raise
            print(f"[ocr] WARN paddle_init_failed, fallback_to_null: {type(exc).__name__}: {exc}", flush=True)
            return NullOcrEngine()

    if strict:
        raise ValueError(f"unsupported_ocr_engine:{engine}")
    return NullOcrEngine()
