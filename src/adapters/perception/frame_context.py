from __future__ import annotations

import os
from pathlib import Path
from time import monotonic, perf_counter
from typing import Any, Protocol


class _CaptureBackend(Protocol):
    def screenshot(self, region: tuple[int, int, int, int] | None = None) -> Any: ...


class FrameContext:
    """Per-tick capture + cache for perception.

    Guarantees:
      - At most one full-screen screenshot per tick (lazy on first use).
      - Each unique ROI is cropped at most once.
      - Each unique (ROI, ocr_profile) is OCR'd at most once.
      - Each unique (element_id, profile) resolves at most once.

    Not thread-safe. Discard at tick boundary.
    """

    def __init__(self, backend: _CaptureBackend) -> None:
        self._backend = backend
        self._full: Any | None = None
        self._full_failed = False
        self._captured_at: float = 0.0
        self._roi_cache: dict[tuple[int, int, int, int], Any] = {}
        self._ocr_cache: dict[tuple[Any, str], str] = {}
        self._element_cache: dict[tuple[str, str], Any] = {}
        self._capture_ms: float = 0.0
        self._ocr_ms: float = 0.0

    @property
    def captured_at(self) -> float:
        return self._captured_at

    def ensure_full(self) -> Any | None:
        if self._full is not None or self._full_failed:
            return self._full
        t0 = perf_counter()
        try:
            img = self._backend.screenshot(region=None)
        except Exception:
            self._full_failed = True
            self._capture_ms += (perf_counter() - t0) * 1000.0
            return None
        self._capture_ms += (perf_counter() - t0) * 1000.0
        if img is None:
            self._full_failed = True
            return None
        self._full = img
        self._captured_at = monotonic()
        return img

    def get_crop(self, region: tuple[int, int, int, int] | None) -> Any | None:
        if region is None:
            return self.ensure_full()
        key = (int(region[0]), int(region[1]), int(region[2]), int(region[3]))
        if key in self._roi_cache:
            return self._roi_cache[key]
        full = self.ensure_full()
        crop: Any | None = None
        if full is not None and hasattr(full, "crop"):
            x, y, w, h = key
            try:
                # PIL.Image.crop expects (left, top, right, bottom).
                crop = full.crop((x, y, x + w, y + h))
            except Exception:
                crop = None
        if crop is None:
            # Fallback for backends whose screenshot() doesn't return a PIL-like
            # object (e.g. test fakes, raw numpy arrays): ask the backend for a
            # per-region capture directly.
            try:
                crop = self._backend.screenshot(region=key)
            except Exception:
                crop = None
        self._roi_cache[key] = crop
        return crop

    def get_ocr_text(
        self,
        region: tuple[int, int, int, int] | None,
        ocr_engine: Any,
        *,
        ocr_key: str = "default",
    ) -> str:
        region_key: Any = (
            (int(region[0]), int(region[1]), int(region[2]), int(region[3]))
            if region is not None
            else None
        )
        cache_key = (region_key, ocr_key)
        cached = self._ocr_cache.get(cache_key)
        if cached is not None:
            return cached
        img = self.get_crop(region)
        if img is None:
            self._ocr_cache[cache_key] = ""
            return ""
        t0 = perf_counter()
        try:
            text = ocr_engine.read_text(img) or ""
        except Exception:
            text = ""
        self._ocr_ms += (perf_counter() - t0) * 1000.0
        self._ocr_cache[cache_key] = text
        return text

    def cached_element(self, element_id: str, profile: str) -> Any | None:
        return self._element_cache.get((element_id, profile))

    def cache_element(self, element_id: str, profile: str, result: Any) -> None:
        self._element_cache[(element_id, profile)] = result

    def stats(self) -> dict[str, Any]:
        return {
            "full_captured": 1 if self._full is not None else 0,
            "roi_crops": len(self._roi_cache),
            "ocr_calls": len(self._ocr_cache),
            "element_hits": len(self._element_cache),
            "capture_ms": round(self._capture_ms, 1),
            "ocr_ms": round(self._ocr_ms, 1),
        }

    def save_full_frame(self, out_dir: str | Path, *, tag: str = "") -> str | None:
        """Best-effort save of the full frame as JPEG for post-mortem debug.

        Returns the file path on success, None otherwise. Intended to be gated
        by an env var at the call site so production runs don't accumulate
        artifacts by default.
        """
        img = self.ensure_full()
        if img is None:
            return None
        try:
            path = Path(out_dir)
            path.mkdir(parents=True, exist_ok=True)
            ts = int(monotonic() * 1000)
            suffix = f"_{tag}" if tag else ""
            fp = path / f"frame_{ts}{suffix}.jpg"
            if hasattr(img, "save"):
                img.save(fp, format="JPEG", quality=70)
            else:
                try:
                    import numpy as np  # noqa: F401
                    import cv2  # type: ignore

                    cv2.imwrite(str(fp), img)
                except Exception:
                    return None
            return str(fp)
        except Exception:
            return None
