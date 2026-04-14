#!/usr/bin/env python3
from __future__ import annotations

import importlib
import os
import shutil
import sys


def check_module(name: str) -> tuple[bool, str]:
    try:
        importlib.import_module(name)
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}:{exc}"


def check_tesseract() -> tuple[bool, str]:
    cmd = os.getenv("TESSERACT_CMD", "").strip()
    if cmd:
        ok = os.path.exists(cmd)
        return ok, f"TESSERACT_CMD={cmd}" if ok else f"TESSERACT_CMD not found: {cmd}"
    on_path = shutil.which("tesseract")
    if on_path:
        return True, f"PATH:{on_path}"
    return False, "tesseract executable not found (set TESSERACT_CMD or add to PATH)"


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
    elif engine == "tesseract":
        checks.extend(
            [
                ("pytesseract", check_module("pytesseract")),
                ("tesseract-exe", check_tesseract()),
            ]
        )
    elif engine == "none":
        pass
    else:
        checks.extend(
            [
                ("paddleocr", check_module("paddleocr")),
                ("paddlepaddle", check_module("paddle")),
            ]
        )

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
