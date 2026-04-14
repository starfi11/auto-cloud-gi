from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any

from src.domain.ui_element import ElementPolicy, MatcherSpec, UiElement


class ElementRegistry:
    def __init__(self, elements: dict[str, UiElement]) -> None:
        self._elements = elements

    def get(self, element_id: str) -> UiElement | None:
        return self._elements.get(element_id)

    @staticmethod
    def from_json(path: str) -> "ElementRegistry":
        p = Path(path)
        if not p.exists():
            return ElementRegistry(elements={})
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return ElementRegistry(elements={})

        raw_elements = data.get("elements", [])
        elements: dict[str, UiElement] = {}
        if not isinstance(raw_elements, list):
            return ElementRegistry(elements={})

        for raw in raw_elements:
            if not isinstance(raw, dict):
                continue
            element_id = str(raw.get("id", "")).strip()
            if not element_id:
                continue
            profile = str(raw.get("profile", "default")).strip() or "default"
            roi = _parse_roi(raw.get("roi"))
            base_size = _parse_base_size(raw.get("base_size"))
            matchers = _parse_matchers(raw.get("matchers"))
            policy = _parse_policy(raw.get("policy"))
            metadata = raw.get("metadata", {}) if isinstance(raw.get("metadata"), dict) else {}
            elements[element_id] = UiElement(
                element_id=element_id,
                profile=profile,
                roi=roi,
                base_size=base_size,
                matchers=matchers,
                policy=policy,
                metadata=metadata,
            )
        return ElementRegistry(elements=elements)



def _parse_roi(v: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(v, (list, tuple)) or len(v) != 4:
        return None
    try:
        x, y, w, h = [int(float(i)) for i in v]
    except (TypeError, ValueError):
        return None
    return x, y, w, h



def _parse_base_size(v: Any) -> tuple[int, int]:
    if not isinstance(v, (list, tuple)) or len(v) != 2:
        return (1600, 900)
    try:
        w, h = [int(float(i)) for i in v]
    except (TypeError, ValueError):
        return (1600, 900)
    return (max(1, w), max(1, h))



def _parse_matchers(v: Any) -> list[MatcherSpec]:
    if not isinstance(v, list):
        return []
    out: list[MatcherSpec] = []
    for raw in v:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind", "")).strip()
        if kind not in {"text_ocr", "template"}:
            continue
        text_any = [str(s) for s in raw.get("text_any", []) if str(s).strip()] if kind == "text_ocr" else []
        template_key = str(raw.get("template_key", "")).strip() if kind == "template" else ""
        confidence = float(raw.get("confidence", 0.9))
        grayscale = bool(raw.get("grayscale", True))
        out.append(
            MatcherSpec(
                kind=kind,  # type: ignore[arg-type]
                text_any=text_any,
                template_key=template_key,
                confidence=confidence,
                grayscale=grayscale,
            )
        )
    return out



def _parse_policy(v: Any) -> ElementPolicy:
    if not isinstance(v, dict):
        return ElementPolicy()
    base = ElementPolicy()
    try:
        return replace(
            base,
            timeout_seconds=float(v.get("timeout_seconds", base.timeout_seconds)),
            poll_seconds=float(v.get("poll_seconds", base.poll_seconds)),
            roi_fail_to_expand=int(v.get("roi_fail_to_expand", base.roi_fail_to_expand)),
            expand_fail_to_global=int(v.get("expand_fail_to_global", base.expand_fail_to_global)),
            roi_expand_factor=float(v.get("roi_expand_factor", base.roi_expand_factor)),
        )
    except (TypeError, ValueError):
        return base
