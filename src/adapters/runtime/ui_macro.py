from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from time import sleep, monotonic
from typing import Any, Protocol

from src.adapters.perception.element_resolver import ElementResolver
from src.adapters.vision import TemplateStore
from src.ports.element_resolver_port import ElementResolverPort


class UiBackend(Protocol):
    def size(self) -> tuple[int, int]:
        ...

    def click(self, x: int, y: int, clicks: int = 1) -> None:
        ...

    def scroll(self, amount: int) -> None:
        ...

    def hotkey(self, *keys: str) -> None:
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


@dataclass
class NoopUiBackend:
    width: int = 1920
    height: int = 1080

    def size(self) -> tuple[int, int]:
        return (self.width, self.height)

    def click(self, x: int, y: int, clicks: int = 1) -> None:
        return None

    def scroll(self, amount: int) -> None:
        return None

    def hotkey(self, *keys: str) -> None:
        return None

    def locate_template(
        self,
        template_path: str,
        *,
        confidence: float = 0.9,
        grayscale: bool = True,
        region: tuple[int, int, int, int] | None = None,
    ) -> tuple[int, int, int, int] | None:
        return None

    def screenshot(self, region: tuple[int, int, int, int] | None = None) -> Any:
        return None


class PyAutoGuiBackend:
    def __init__(self) -> None:
        import pyautogui  # type: ignore

        self._pg = pyautogui
        self._pg.FAILSAFE = True

    def size(self) -> tuple[int, int]:
        size = self._pg.size()
        return int(size.width), int(size.height)

    def click(self, x: int, y: int, clicks: int = 1) -> None:
        self._pg.click(x=x, y=y, clicks=max(1, clicks))

    def scroll(self, amount: int) -> None:
        self._pg.scroll(amount)

    def hotkey(self, *keys: str) -> None:
        self._pg.hotkey(*keys)

    def locate_template(
        self,
        template_path: str,
        *,
        confidence: float = 0.9,
        grayscale: bool = True,
        region: tuple[int, int, int, int] | None = None,
    ) -> tuple[int, int, int, int] | None:
        kwargs: dict[str, Any] = {"grayscale": bool(grayscale)}
        if region is not None:
            kwargs["region"] = region
        try:
            kwargs["confidence"] = float(confidence)
            box = self._pg.locateOnScreen(template_path, **kwargs)
        except Exception:
            kwargs.pop("confidence", None)
            box = self._pg.locateOnScreen(template_path, **kwargs)
        if box is None:
            return None
        return int(box.left), int(box.top), int(box.width), int(box.height)

    def screenshot(self, region: tuple[int, int, int, int] | None = None) -> Any:
        if region is None:
            return self._pg.screenshot()
        x, y, w, h = region
        return self._pg.screenshot(region=(x, y, w, h))


class DxcamBackend:
    """Capture-only backend using DXGI Desktop Duplication via dxcam.

    Captures DirectX / hardware-overlay content that GDI-based backends
    (pyautogui, PIL.ImageGrab) cannot see. Input ops (click/hotkey/etc.)
    are not implemented — use HybridBackend to pair this with an input
    backend.
    """

    def __init__(self, output_idx: int | None = None) -> None:
        import dxcam  # type: ignore

        self._dxcam = dxcam
        kwargs: dict[str, Any] = {"output_color": "RGB"}
        if output_idx is not None:
            kwargs["output_idx"] = int(output_idx)
        cam = dxcam.create(**kwargs)
        if cam is None:
            raise RuntimeError("dxcam_create_returned_none")
        self._cam = cam
        # Warm-up: first grab after create is often None; force a real frame
        # so the size probe and first real capture succeed.
        first = self._grab_raw(None, retries=10, delay=0.02)
        if first is None:
            raise RuntimeError("dxcam_warmup_failed")
        h, w = first.shape[:2]
        self._width = int(w)
        self._height = int(h)

    def size(self) -> tuple[int, int]:
        return self._width, self._height

    def click(self, x: int, y: int, clicks: int = 1) -> None:  # pragma: no cover
        raise NotImplementedError("DxcamBackend is capture-only")

    def scroll(self, amount: int) -> None:  # pragma: no cover
        raise NotImplementedError("DxcamBackend is capture-only")

    def hotkey(self, *keys: str) -> None:  # pragma: no cover
        raise NotImplementedError("DxcamBackend is capture-only")

    def _grab_raw(
        self,
        region: tuple[int, int, int, int] | None,
        *,
        retries: int = 5,
        delay: float = 0.005,
    ):
        # dxcam region is (left, top, right, bottom); our region is (x, y, w, h).
        rg = None
        if region is not None:
            x, y, w, h = region
            rg = (int(x), int(y), int(x + w), int(y + h))
        deadline = monotonic() + max(0.0, retries * delay)
        attempt = 0
        while True:
            frame = self._cam.grab(region=rg) if rg else self._cam.grab()
            if frame is not None:
                return frame
            attempt += 1
            if attempt >= retries or monotonic() >= deadline:
                return None
            sleep(delay)

    def screenshot(self, region: tuple[int, int, int, int] | None = None) -> Any:
        frame = self._grab_raw(region)
        if frame is None:
            return None
        try:
            from PIL import Image  # type: ignore

            return Image.fromarray(frame)
        except Exception:
            return frame  # numpy RGB array fallback

    def locate_template(
        self,
        template_path: str,
        *,
        confidence: float = 0.9,
        grayscale: bool = True,
        region: tuple[int, int, int, int] | None = None,
    ) -> tuple[int, int, int, int] | None:
        try:
            import cv2  # type: ignore
            import numpy as np  # type: ignore
        except Exception:
            return None
        frame = self._grab_raw(region)
        if frame is None:
            return None
        tmpl_flag = cv2.IMREAD_GRAYSCALE if grayscale else cv2.IMREAD_COLOR
        tmpl = cv2.imread(template_path, tmpl_flag)
        if tmpl is None:
            return None
        haystack = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY) if grayscale else cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        if haystack.shape[0] < tmpl.shape[0] or haystack.shape[1] < tmpl.shape[1]:
            return None
        res = cv2.matchTemplate(haystack, tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if float(max_val) < float(confidence):
            return None
        th, tw = tmpl.shape[:2]
        mx, my = int(max_loc[0]), int(max_loc[1])
        if region is not None:
            mx += int(region[0])
            my += int(region[1])
        return mx, my, int(tw), int(th)


class HybridBackend:
    """Capture via dxcam, input via pyautogui.

    dxcam sees DirectX content; pyautogui handles click/scroll/hotkey
    reliably. Template matching runs against dxcam frames via cv2, so it
    stays consistent with what the rest of the perception layer sees.
    """

    def __init__(self, output_idx: int | None = None) -> None:
        self._input = PyAutoGuiBackend()
        self._cam = DxcamBackend(output_idx=output_idx)

    def size(self) -> tuple[int, int]:
        return self._input.size()

    def click(self, x: int, y: int, clicks: int = 1) -> None:
        self._input.click(x, y, clicks=clicks)

    def scroll(self, amount: int) -> None:
        self._input.scroll(amount)

    def hotkey(self, *keys: str) -> None:
        self._input.hotkey(*keys)

    def screenshot(self, region: tuple[int, int, int, int] | None = None) -> Any:
        return self._cam.screenshot(region=region)

    def locate_template(
        self,
        template_path: str,
        *,
        confidence: float = 0.9,
        grayscale: bool = True,
        region: tuple[int, int, int, int] | None = None,
    ) -> tuple[int, int, int, int] | None:
        return self._cam.locate_template(
            template_path,
            confidence=confidence,
            grayscale=grayscale,
            region=region,
        )


def build_ui_backend(mode: str = "auto") -> UiBackend:
    m = mode.strip().lower()
    if m == "noop":
        return NoopUiBackend()
    if m == "pyautogui":
        return PyAutoGuiBackend()
    if m in {"dxcam", "hybrid"}:
        return HybridBackend()
    if m == "auto":
        try:
            return HybridBackend()
        except Exception:
            pass
        try:
            return PyAutoGuiBackend()
        except Exception:
            return NoopUiBackend()
    return NoopUiBackend()


@dataclass(frozen=True)
class MacroStepResult:
    op: str
    ok: bool
    detail: str


class UiMacroExecutor:
    def __init__(self, backend: UiBackend, element_resolver: ElementResolverPort | None = None) -> None:
        self._backend = backend
        template_root = (
            os.getenv("VISION_TEMPLATE_ROOT", "").strip()
            or os.getenv("VISION_TEMPLATE_DIR", "").strip()
            or "./runtime/vision/templates"
        )
        self._template_store = TemplateStore(template_root)
        self._elements = element_resolver or ElementResolver(backend)

    def execute(self, steps: list[dict[str, Any]]) -> list[MacroStepResult]:
        results: list[MacroStepResult] = []
        for idx, step in enumerate(steps):
            op = str(step.get("op", "")).strip().lower()
            if not op:
                results.append(MacroStepResult(op="unknown", ok=False, detail=f"missing_op@{idx}"))
                continue
            try:
                if op == "sleep":
                    sleep(float(step.get("seconds", 0.1)))
                    results.append(MacroStepResult(op=op, ok=True, detail="slept"))
                    continue
                if op == "click":
                    x, y = self._resolve_xy(step)
                    self._backend.click(x, y, clicks=int(step.get("clicks", 1)))
                    results.append(MacroStepResult(op=op, ok=True, detail=f"click@{x},{y}"))
                    self._after(step)
                    continue
                if op == "scroll":
                    self._backend.scroll(int(step.get("amount", -200)))
                    results.append(MacroStepResult(op=op, ok=True, detail=f"scroll:{int(step.get('amount', -200))}"))
                    self._after(step)
                    continue
                if op == "hotkey":
                    keys = [str(k) for k in step.get("keys", []) if str(k).strip()]
                    if not keys:
                        results.append(MacroStepResult(op=op, ok=False, detail="no_keys"))
                        continue
                    self._backend.hotkey(*keys)
                    results.append(MacroStepResult(op=op, ok=True, detail=f"hotkey:{'+'.join(keys)}"))
                    self._after(step)
                    continue
                if op == "wait_template":
                    found = self._wait_template(step, present=True)
                    if found is None:
                        if bool(step.get("optional", False)):
                            results.append(MacroStepResult(op=op, ok=True, detail="template_optional_not_found"))
                            continue
                        results.append(MacroStepResult(op=op, ok=False, detail="template_not_found"))
                        continue
                    results.append(MacroStepResult(op=op, ok=True, detail=f"template_found@{found[0]},{found[1]}"))
                    self._after(step)
                    continue
                if op == "wait_template_gone":
                    gone = self._wait_template_gone(step)
                    if not gone:
                        if bool(step.get("optional", False)):
                            results.append(MacroStepResult(op=op, ok=True, detail="template_optional_still_present"))
                            continue
                        results.append(MacroStepResult(op=op, ok=False, detail="template_still_present"))
                        continue
                    results.append(MacroStepResult(op=op, ok=True, detail="template_gone"))
                    self._after(step)
                    continue
                if op == "click_template":
                    found = self._wait_template(step, present=True)
                    if found is None:
                        if bool(step.get("optional", False)):
                            results.append(MacroStepResult(op=op, ok=True, detail="template_optional_not_found"))
                            continue
                        results.append(MacroStepResult(op=op, ok=False, detail="template_not_found"))
                        continue
                    cx = int(found[0] + found[2] * float(step.get("anchor_x", 0.5)))
                    cy = int(found[1] + found[3] * float(step.get("anchor_y", 0.5)))
                    self._backend.click(cx, cy, clicks=int(step.get("clicks", 1)))
                    results.append(MacroStepResult(op=op, ok=True, detail=f"click_template@{cx},{cy}"))
                    self._after(step)
                    continue
                if op == "wait_element":
                    element_id = str(step.get("element_id", "")).strip()
                    if not element_id:
                        results.append(MacroStepResult(op=op, ok=False, detail="missing_element_id"))
                        continue
                    profile = str(step.get("element_profile", "default")).strip() or "default"
                    resolved = self._elements.resolve(
                        element_id=element_id,
                        profile=profile,
                        timeout_seconds=float(step.get("timeout_seconds", 8.0)),
                        poll_seconds=float(step.get("poll_seconds", 0.25)),
                    )
                    if not resolved.ok:
                        if bool(step.get("optional", False)):
                            results.append(MacroStepResult(op=op, ok=True, detail=f"element_optional_miss:{resolved.detail}"))
                            continue
                        results.append(MacroStepResult(op=op, ok=False, detail=f"element_miss:{resolved.detail}"))
                        continue
                    hit_detail = f"element_hit:{element_id}:{resolved.matcher_kind}:{resolved.detail}"
                    if resolved.matched_text:
                        hit_detail = f"{hit_detail}:matched={resolved.matched_text}"
                    results.append(MacroStepResult(op=op, ok=True, detail=hit_detail))
                    self._after(step)
                    continue
                if op == "click_element":
                    element_id = str(step.get("element_id", "")).strip()
                    if not element_id:
                        results.append(MacroStepResult(op=op, ok=False, detail="missing_element_id"))
                        continue
                    profile = str(step.get("element_profile", "default")).strip() or "default"
                    resolved = self._elements.resolve(
                        element_id=element_id,
                        profile=profile,
                        timeout_seconds=float(step.get("timeout_seconds", 8.0)),
                        poll_seconds=float(step.get("poll_seconds", 0.25)),
                    )
                    if not resolved.ok or resolved.bbox is None:
                        if bool(step.get("optional", False)):
                            results.append(MacroStepResult(op=op, ok=True, detail=f"element_optional_miss:{resolved.detail}"))
                            continue
                        results.append(MacroStepResult(op=op, ok=False, detail=f"element_miss:{resolved.detail}"))
                        continue
                    bx, by, bw, bh = resolved.bbox
                    cx = int(bx + bw * float(step.get("anchor_x", 0.5)))
                    cy = int(by + bh * float(step.get("anchor_y", 0.5)))
                    self._backend.click(cx, cy, clicks=int(step.get("clicks", 1)))
                    hit_detail = f"click_element@{cx},{cy}:{element_id}:{resolved.matcher_kind}:{resolved.detail}"
                    if resolved.matched_text:
                        hit_detail = f"{hit_detail}:matched={resolved.matched_text}"
                    results.append(MacroStepResult(op=op, ok=True, detail=hit_detail))
                    self._after(step)
                    continue
                results.append(MacroStepResult(op=op, ok=False, detail=f"unsupported_op:{op}"))
            except Exception as exc:
                results.append(MacroStepResult(op=op, ok=False, detail=f"error:{exc}"))
        return results

    def _resolve_xy(self, step: dict[str, Any]) -> tuple[int, int]:
        if "nx" in step and "ny" in step:
            w, h = self._backend.size()
            nx = max(0.0, min(1.0, float(step["nx"])))
            ny = max(0.0, min(1.0, float(step["ny"])))
            return int(w * nx), int(h * ny)

        x = float(step.get("x", 0))
        y = float(step.get("y", 0))
        base_w = float(step.get("base_w", 1600.0))
        base_h = float(step.get("base_h", 900.0))
        w, h = self._backend.size()
        sx = w / max(1.0, base_w)
        sy = h / max(1.0, base_h)
        return int(x * sx), int(y * sy)

    def _after(self, step: dict[str, Any]) -> None:
        delay = float(step.get("after_sleep", 0.0))
        if delay > 0:
            sleep(delay)

    def _resolve_template_path(self, step: dict[str, Any]) -> str:
        explicit = str(step.get("template_path", "")).strip()
        if explicit:
            p = Path(explicit)
            if p.exists():
                return str(p)
        key = str(step.get("template_key", "")).strip()
        if not key:
            raise ValueError("missing_template_key")
        profile = str(step.get("template_profile", "default")).strip() or "default"
        return self._template_store.resolve(key, profile=profile).path

    def _resolve_region(self, step: dict[str, Any]) -> tuple[int, int, int, int] | None:
        raw = step.get("region")
        if not isinstance(raw, (list, tuple)) or len(raw) != 4:
            return None
        x, y, w, h = [float(v) for v in raw]
        base_w = float(step.get("base_w", 1600.0))
        base_h = float(step.get("base_h", 900.0))
        sw, sh = self._backend.size()
        sx = sw / max(1.0, base_w)
        sy = sh / max(1.0, base_h)
        return int(x * sx), int(y * sy), int(w * sx), int(h * sy)

    def _wait_template(self, step: dict[str, Any], *, present: bool) -> tuple[int, int, int, int] | None:
        template_path = self._resolve_template_path(step)
        timeout = float(step.get("timeout_seconds", 8.0))
        poll = max(0.05, float(step.get("poll_seconds", 0.25)))
        confidence = float(step.get("confidence", 0.9))
        grayscale = bool(step.get("grayscale", True))
        region = self._resolve_region(step)

        waited = 0.0
        while waited <= timeout:
            box = self._backend.locate_template(
                template_path,
                confidence=confidence,
                grayscale=grayscale,
                region=region,
            )
            if present and box is not None:
                return box
            if (not present) and box is None:
                return None
            sleep(poll)
            waited += poll
        return None

    def _wait_template_gone(self, step: dict[str, Any]) -> bool:
        template_path = self._resolve_template_path(step)
        timeout = float(step.get("timeout_seconds", 8.0))
        poll = max(0.05, float(step.get("poll_seconds", 0.25)))
        confidence = float(step.get("confidence", 0.9))
        grayscale = bool(step.get("grayscale", True))
        region = self._resolve_region(step)

        waited = 0.0
        while waited <= timeout:
            box = self._backend.locate_template(
                template_path,
                confidence=confidence,
                grayscale=grayscale,
                region=region,
            )
            if box is None:
                return True
            sleep(poll)
            waited += poll
        return False
