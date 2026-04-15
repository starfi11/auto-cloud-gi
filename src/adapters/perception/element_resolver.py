from __future__ import annotations

import os
from time import monotonic, sleep
from typing import Any, Protocol

from src.adapters.perception.element_registry import ElementRegistry
from src.adapters.perception.frame_context import FrameContext
from src.adapters.vision import TemplateStore, build_ocr_engine
from src.domain.ui_element import ElementMatchResult, MatcherSpec, UiElement
from src.ports.element_resolver_port import ElementResolverPort
from src.ports.ocr_engine_port import OcrEnginePort


class UiSenseBackend(Protocol):
    def size(self) -> tuple[int, int]:
        ...

    def locate_template(
        self,
        template_path: str,
        *,
        confidence: float = 0.9,
        grayscale: bool = True,
        region: tuple[int, int, int, int] | None = None,
    ) -> tuple[int, int, int, int] | None:
        ...

    def screenshot(self, region: tuple[int, int, int, int] | None = None) -> Any:
        ...


class ElementResolver(ElementResolverPort):
    def __init__(
        self,
        backend: UiSenseBackend,
        *,
        registry: ElementRegistry | None = None,
        template_root: str | None = None,
        ocr_engine: OcrEnginePort | None = None,
    ) -> None:
        self._backend = backend
        self._registry = registry or ElementRegistry.from_json(
            os.getenv("VISION_ELEMENT_SPEC", "./runtime/vision/elements.json")
        )
        template_env = (
            template_root
            or os.getenv("VISION_TEMPLATE_ROOT", "").strip()
            or os.getenv("VISION_TEMPLATE_DIR", "").strip()
            or "./runtime/vision/templates"
        )
        self._template_store = TemplateStore(template_env)
        self._ocr = ocr_engine or build_ocr_engine()

    def resolve(
        self,
        *,
        element_id: str,
        profile: str = "default",
        timeout_seconds: float | None = None,
        poll_seconds: float | None = None,
    ) -> ElementMatchResult:
        element = self._registry.get(element_id)
        if element is None:
            return ElementMatchResult(ok=False, element_id=element_id, detail="element_not_found")

        timeout = float(timeout_seconds) if timeout_seconds is not None else element.policy.timeout_seconds
        poll = float(poll_seconds) if poll_seconds is not None else element.policy.poll_seconds

        fail_count = 0
        t0 = monotonic()
        last_phase = "roi"
        while True:
            phase = self._phase_for_fail_count(fail_count, element)
            last_phase = phase
            # Fresh frame per iteration: per-iteration cache, but cross-iteration
            # must re-capture since we are explicitly waiting for the screen to change.
            frame = FrameContext(self._backend)
            region = self._region_for_phase(element, phase)
            for matcher in self._ordered_matchers(element.matchers):
                found = self._try_match(
                    matcher=matcher,
                    element=element,
                    profile=profile,
                    region=region,
                    frame=frame,
                )
                if found.ok:
                    return found
            fail_count += 1
            elapsed = monotonic() - t0
            if elapsed >= timeout:
                return ElementMatchResult(
                    ok=False,
                    element_id=element.element_id,
                    detail=f"element_timeout:{last_phase}",
                )
            remaining = max(0.0, timeout - elapsed)
            sleep_for = min(max(0.001, poll), remaining)
            if sleep_for > 0:
                sleep(sleep_for)

    def resolve_once(
        self,
        *,
        element_id: str,
        profile: str = "default",
        frame: FrameContext,
    ) -> ElementMatchResult:
        """Single-frame resolution. Shares capture/OCR cache via FrameContext.

        Tries roi -> expand -> global in sequence within the one frame. No
        sleeping, no retries — tick loop owns waiting semantics.
        """
        element = self._registry.get(element_id)
        if element is None:
            return ElementMatchResult(ok=False, element_id=element_id, detail="element_not_found")

        cache_key = (element_id, profile)
        cached = frame.cached_element(element_id, profile)
        if cached is not None:
            return cached  # type: ignore[return-value]

        last_detail = "element_miss"
        for phase in ("roi", "expand", "global"):
            region = self._region_for_phase(element, phase)
            for matcher in self._ordered_matchers(element.matchers):
                found = self._try_match(
                    matcher=matcher,
                    element=element,
                    profile=profile,
                    region=region,
                    frame=frame,
                )
                if found.ok:
                    frame.cache_element(*cache_key, found)
                    return found
                last_detail = found.detail
        miss = ElementMatchResult(
            ok=False,
            element_id=element.element_id,
            detail=f"element_miss:{last_detail}",
        )
        frame.cache_element(*cache_key, miss)
        return miss

    def _phase_for_fail_count(self, fail_count: int, element: UiElement) -> str:
        if fail_count < max(1, int(element.policy.roi_fail_to_expand)):
            return "roi"
        if fail_count < max(element.policy.roi_fail_to_expand + 1, int(element.policy.expand_fail_to_global)):
            return "expand"
        return "global"

    def _region_for_phase(self, element: UiElement, phase: str) -> tuple[int, int, int, int] | None:
        if element.roi is None or phase == "global":
            return None
        scaled = self._scale_region(element.roi, element.base_size)
        if phase == "roi":
            return scaled
        return self._expand_region(scaled, element.policy.roi_expand_factor)

    def _scale_region(self, region: tuple[int, int, int, int], base_size: tuple[int, int]) -> tuple[int, int, int, int]:
        x, y, w, h = region
        bw, bh = base_size
        sw, sh = self._backend.size()
        sx = sw / max(1, bw)
        sy = sh / max(1, bh)
        return int(x * sx), int(y * sy), max(1, int(w * sx)), max(1, int(h * sy))

    def _expand_region(self, region: tuple[int, int, int, int], factor: float) -> tuple[int, int, int, int]:
        x, y, w, h = region
        sw, sh = self._backend.size()
        cx = x + w // 2
        cy = y + h // 2
        nw = max(1, int(w * max(1.0, factor)))
        nh = max(1, int(h * max(1.0, factor)))
        nx = max(0, cx - nw // 2)
        ny = max(0, cy - nh // 2)
        if nx + nw > sw:
            nw = sw - nx
        if ny + nh > sh:
            nh = sh - ny
        return nx, ny, max(1, nw), max(1, nh)

    def _ordered_matchers(self, matchers: list[MatcherSpec]) -> list[MatcherSpec]:
        # Text-first, then template fallback.
        return sorted(matchers, key=lambda m: 0 if m.kind == "text_ocr" else 1)

    def _try_match(
        self,
        *,
        matcher: MatcherSpec,
        element: UiElement,
        profile: str,
        region: tuple[int, int, int, int] | None,
        frame: FrameContext,
    ) -> ElementMatchResult:
        if matcher.kind == "text_ocr":
            return self._match_text(element, matcher, region, frame)
        if matcher.kind == "template":
            return self._match_template(element, matcher, profile, region)
        return ElementMatchResult(ok=False, element_id=element.element_id, detail=f"unsupported_matcher:{matcher.kind}")

    def _match_template(
        self,
        element: UiElement,
        matcher: MatcherSpec,
        profile: str,
        region: tuple[int, int, int, int] | None,
    ) -> ElementMatchResult:
        key = matcher.template_key.strip()
        if not key:
            return ElementMatchResult(ok=False, element_id=element.element_id, detail="template_key_missing")
        try:
            tr = self._template_store.resolve(key, profile=profile or element.profile)
        except Exception:
            return ElementMatchResult(ok=False, element_id=element.element_id, detail=f"template_not_found:{key}")

        try:
            box = self._backend.locate_template(
                tr.path,
                confidence=float(matcher.confidence),
                grayscale=bool(matcher.grayscale),
                region=region,
            )
        except Exception as exc:  # noqa: BLE001
            return ElementMatchResult(
                ok=False,
                element_id=element.element_id,
                detail=f"template_error:{type(exc).__name__}:{exc}",
            )
        if box is None:
            return ElementMatchResult(ok=False, element_id=element.element_id, detail="template_miss")
        return ElementMatchResult(
            ok=True,
            element_id=element.element_id,
            matcher_kind="template",
            confidence=float(matcher.confidence),
            bbox=box,
            evidence_refs=[f"template:{tr.path}"],
            detail="template_hit",
        )

    def _match_text(
        self,
        element: UiElement,
        matcher: MatcherSpec,
        region: tuple[int, int, int, int] | None,
        frame: FrameContext,
    ) -> ElementMatchResult:
        if not matcher.text_any:
            return ElementMatchResult(ok=False, element_id=element.element_id, detail="text_terms_missing")
        try:
            text = frame.get_ocr_text(region, self._ocr)
        except Exception as exc:  # noqa: BLE001
            return ElementMatchResult(
                ok=False,
                element_id=element.element_id,
                detail=f"text_error:{type(exc).__name__}:{exc}",
            )
        text_lower = text.lower()
        preview = self._preview_text(text)
        for term in matcher.text_any:
            if term and term.lower() in text_lower:
                return ElementMatchResult(
                    ok=True,
                    element_id=element.element_id,
                    matcher_kind="text_ocr",
                    confidence=0.75,
                    bbox=region,
                    matched_text=term,
                    evidence_refs=["ocr:screen"],
                    detail=f"text_hit:{term};ocr={preview}",
                )
        return ElementMatchResult(
            ok=False,
            element_id=element.element_id,
            detail=f"text_miss;ocr={preview}",
        )

    def _preview_text(self, raw: str, limit: int = 60) -> str:
        cleaned = " ".join(str(raw).split())
        if not cleaned:
            return "<empty>"
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[:limit] + "..."
