#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip().strip('"').strip("'")

from src.adapters.perception.element_registry import ElementRegistry
from src.adapters.perception.element_resolver import ElementResolver
from src.adapters.runtime.ui_macro import build_ui_backend
from src.adapters.vision import build_ocr_engine


@dataclass
class ProbeResult:
    attempt: int
    ok: bool
    detail: str
    matched_text: str
    bbox: tuple[int, int, int, int] | None
    matcher_kind: str


def _scale_roi(roi: tuple[int, int, int, int], base_size: tuple[int, int], screen_size: tuple[int, int]) -> tuple[int, int, int, int]:
    x, y, w, h = roi
    bw, bh = base_size
    sw, sh = screen_size
    sx = sw / max(1, bw)
    sy = sh / max(1, bh)
    return int(x * sx), int(y * sy), max(1, int(w * sx)), max(1, int(h * sy))


def _save_image(image: Any, path: Path) -> None:
    if image is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
    except Exception:
        return


def main() -> int:
    _load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(description="Probe OCR/template matching for start-game element.")
    parser.add_argument("--element-id", default="cloud_start_game_button")
    parser.add_argument("--profile", default="genshin_cloud")
    parser.add_argument("--attempts", type=int, default=8)
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=float, default=1.5)
    parser.add_argument("--poll-seconds", type=float, default=0.15)
    parser.add_argument("--dump-dir", default="./runtime/debug_frames")
    parser.add_argument("--dump-images", action="store_true")
    parser.add_argument("--element-spec", default=os.getenv("VISION_ELEMENT_SPEC", "./runtime/vision/elements.json"))
    parser.add_argument(
        "--template-root",
        default=os.getenv("VISION_TEMPLATE_ROOT", "").strip()
        or os.getenv("VISION_TEMPLATE_DIR", "").strip()
        or "./runtime/vision/templates",
    )
    parser.add_argument("--backend", default=os.getenv("UI_AUTOMATION_BACKEND", "auto"))
    parser.add_argument("--ocr-engine", default=os.getenv("OCR_ENGINE", "paddle"), choices=["paddle", "none"])
    parser.add_argument("--ocr-lang", default=os.getenv("OCR_LANG", "eng+chi_sim"))
    args = parser.parse_args()
    os.environ["OCR_ENGINE"] = args.ocr_engine
    os.environ["OCR_LANG"] = args.ocr_lang
    os.environ["OCR_ENGINE_STRICT"] = "true"

    backend = build_ui_backend(args.backend)
    screen = backend.size()
    print(f"[probe] backend={args.backend} screen={screen} ocr_engine={args.ocr_engine} ocr_lang={args.ocr_lang}")

    registry = ElementRegistry.from_json(args.element_spec)
    element = registry.get(args.element_id)
    if element is None:
        print(f"[probe] ERROR element not found: {args.element_id}")
        return 2
    print(
        f"[probe] element={element.element_id} profile={element.profile} "
        f"roi={element.roi} base={element.base_size} matchers={[m.kind for m in element.matchers]}"
    )

    ocr = build_ocr_engine()
    print(f"[probe] resolved_ocr_impl={ocr.__class__.__name__} strict={os.getenv('OCR_ENGINE_STRICT')}")
    resolver = ElementResolver(
        backend,
        registry=registry,
        template_root=args.template_root,
        ocr_engine=ocr,
    )

    scaled_roi = _scale_roi(element.roi, element.base_size, screen) if element.roi is not None else None
    if scaled_roi is not None:
        print(f"[probe] scaled_roi={scaled_roi}")
    else:
        print("[probe] scaled_roi=<global>")

    results: list[ProbeResult] = []
    dump_root = Path(args.dump_dir)

    for i in range(1, max(1, args.attempts) + 1):
        ts = int(time.time() * 1000)
        full_img = backend.screenshot(region=None)
        roi_img = backend.screenshot(region=scaled_roi) if scaled_roi is not None else full_img
        if args.dump_images:
            _save_image(full_img, dump_root / f"{ts}_full_{i}.png")
            _save_image(roi_img, dump_root / f"{ts}_roi_{i}.png")

        match = resolver.resolve(
            element_id=args.element_id,
            profile=args.profile,
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
        )
        r = ProbeResult(
            attempt=i,
            ok=match.ok,
            detail=match.detail,
            matched_text=match.matched_text,
            bbox=match.bbox,
            matcher_kind=match.matcher_kind,
        )
        results.append(r)
        print(
            f"[probe] attempt={r.attempt} ok={r.ok} matcher={r.matcher_kind or '-'} "
            f"matched={r.matched_text or '-'} bbox={r.bbox} detail={r.detail}"
        )
        last_text = str(getattr(ocr, "last_text", "") or "")
        if last_text:
            preview = " ".join(last_text.split())
            if len(preview) > 120:
                preview = preview[:120] + "..."
            print(f"[probe] ocr_preview={preview}")

        if i < args.attempts:
            time.sleep(max(0.1, args.interval_seconds))

    hits = sum(1 for x in results if x.ok)
    print(f"[probe] summary hits={hits}/{len(results)}")
    return 0 if hits > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
