from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

MatcherKind = Literal["text_ocr", "template"]


@dataclass(frozen=True)
class MatcherSpec:
    kind: MatcherKind
    text_any: list[str] = field(default_factory=list)
    template_key: str = ""
    confidence: float = 0.9
    grayscale: bool = True


@dataclass(frozen=True)
class ElementPolicy:
    timeout_seconds: float = 8.0
    poll_seconds: float = 0.25
    roi_fail_to_expand: int = 3
    expand_fail_to_global: int = 6
    roi_expand_factor: float = 1.6


@dataclass(frozen=True)
class UiElement:
    element_id: str
    profile: str = "default"
    roi: tuple[int, int, int, int] | None = None
    base_size: tuple[int, int] = (1600, 900)
    matchers: list[MatcherSpec] = field(default_factory=list)
    policy: ElementPolicy = field(default_factory=ElementPolicy)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ElementMatchResult:
    ok: bool
    element_id: str
    matcher_kind: str = ""
    confidence: float = 0.0
    bbox: tuple[int, int, int, int] | None = None
    matched_text: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    detail: str = ""
