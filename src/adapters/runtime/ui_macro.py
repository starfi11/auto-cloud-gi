from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from typing import Any, Protocol


class UiBackend(Protocol):
    def size(self) -> tuple[int, int]:
        ...

    def click(self, x: int, y: int, clicks: int = 1) -> None:
        ...

    def scroll(self, amount: int) -> None:
        ...

    def hotkey(self, *keys: str) -> None:
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


def build_ui_backend(mode: str = "auto") -> UiBackend:
    m = mode.strip().lower()
    if m == "noop":
        return NoopUiBackend()
    if m == "pyautogui":
        return PyAutoGuiBackend()
    if m == "auto":
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
    def __init__(self, backend: UiBackend) -> None:
        self._backend = backend

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
