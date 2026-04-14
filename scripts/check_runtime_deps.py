#!/usr/bin/env python3
from __future__ import annotations

import importlib
import os


def check_module(name: str) -> tuple[bool, str]:
    try:
        importlib.import_module(name)
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}:{exc}"


def main() -> int:
    engine = os.getenv("OCR_ENGINE", "paddle").strip().lower()
    checks = [("pyautogui", check_module("pyautogui"))]
    if engine == "paddle":
        checks.extend(
            [
                ("paddleocr", check_module("paddleocr")),
                ("paddlepaddle", check_module("paddle")),
            ]
        )
    elif engine == "none":
        pass
    else:
        checks.append(("ocr_engine", (False, f"unsupported OCR_ENGINE={engine}, expected paddle|none")))

    all_ok = True
    print(f"[deps] runtime dependency check (OCR_ENGINE={engine})")
    for name, (ok, detail) in checks:
        status = "OK" if ok else "MISSING"
        print(f"[deps] {name}: {status} ({detail})")
        all_ok = all_ok and ok

    t_root = os.getenv("VISION_TEMPLATE_ROOT", "").strip()
    t_dir = os.getenv("VISION_TEMPLATE_DIR", "").strip()
    if t_root and t_dir and t_root != t_dir:
        print(f"[deps] WARN template env mismatch: VISION_TEMPLATE_ROOT={t_root}, VISION_TEMPLATE_DIR={t_dir}")

    if not all_ok:
        print("[deps] FAIL: install missing deps before smoke run")
        return 1
    print("[deps] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
