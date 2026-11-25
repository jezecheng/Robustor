"""生成 3 页 A4 数学作业样例图 + canned 识别结果（mock provider 的数据源）。

用法：cd apps/api && .venv/bin/python ../../scripts/gen_fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

from app.config import CANNED_PATH, FIXTURE_DEMO_DIR  # noqa: E402

W, H = 1240, 1754
INK = "#1b1b1b"
RED = "#c62828"
BLUE = "#1d4ed8"

HAND_FONTS = [
    "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf",
    "/System/Library/Fonts/Supplemental/Chalkboard.ttc",
]
SANS_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]
MONO_FONTS = [
    "/System/Library/Fonts/Supplemental/Courier New.ttf",
]

PAGE_SPECS = [
    {
        "idx": 1,
        "title": "Unit 3 · Quadratic Equations",
        "regions": [
            {"block_type": "stem", "ink_role": "print", "bbox": [0.07, 0.09, 0.86, 0.08],
             "text": "1. Solve   x^2 - 5x + 6 = 0", "color": INK, "size": 38, "conf": 0.97},
            {"block_type": "figure", "ink_role": "print", "bbox": [0.09, 0.19, 0.34, 0.16],
             "draw": "axes", "conf": 0.90},
            {"block_type": "answer", "ink_role": "answer", "bbox": [0.09, 0.39, 0.42, 0.07],
             "text": "x = 1,  x = 6", "color": INK, "size": 40, "hand": True, "conf": 0.86},
            {"block_type": "mark", "ink_role": "mark", "bbox": [0.56, 0.385, 0.10, 0.075],
             "symbol": "✗", "conf": 0.93},
            {"block_type": "correction", "ink_role": "correction", "bbox": [0.09, 0.49, 0.80, 0.08],
             "text": "x^2 - 5x + 6 = (x - 2)(x - 3)", "color": BLUE, "size": 34, "hand": True, "conf": 0.88},
            {"block_type": "correction", "ink_role": "correction", "bbox": [0.09, 0.58, 0.62, 0.07],
             "text": "so  x = 2  or  x = 3", "color": BLUE, "size": 36, "hand": True, "conf": 0.87},
        ],
    },
    {
        "idx": 2,
        "title": "Unit 3 · Practice",
        "regions": [
            {"block_type": "stem", "ink_role": "print", "bbox": [0.07, 0.09, 0.86, 0.08],
             "text": "2. Solve   2x^2 + 3x - 2 = 0", "color": INK, "size": 38, "conf": 0.96},
            {"block_type": "answer", "ink_role": "answer", "bbox": [0.09, 0.20, 0.44, 0.07],
             "text": "x = 1/2,  x = -2", "color": INK, "size": 40, "hand": True, "conf": 0.90},
            {"block_type": "mark", "ink_role": "mark", "bbox": [0.58, 0.195, 0.09, 0.075],
             "symbol": "✓", "conf": 0.95},
            {"block_type": "stem", "ink_role": "print", "bbox": [0.07, 0.34, 0.86, 0.10],
             "text": "3. In triangle ABC, AB = 5, AC = 12,", "color": INK, "size": 34, "conf": 0.95,
             "page_start": 2, "page_end": 3},
        ],
    },
    {
        "idx": 3,
        "title": "Unit 3 · Practice (cont.)",
        "regions": [
            {"block_type": "stem", "ink_role": "print", "bbox": [0.07, 0.09, 0.86, 0.08],
             "text": "angle A = 90 deg. Find BC and the area.", "color": INK, "size": 34, "conf": 0.94,
             "page_start": 2, "page_end": 3},
            {"block_type": "figure", "ink_role": "print", "bbox": [0.09, 0.20, 0.32, 0.18],
             "draw": "triangle", "conf": 0.91},
            {"block_type": "answer", "ink_role": "answer", "bbox": [0.50, 0.24, 0.42, 0.08],
             "text": "BC = 13,  Area = 30", "color": INK, "size": 38, "hand": True, "conf": 0.89},
            {"block_type": "mark", "ink_role": "mark", "bbox": [0.50, 0.335, 0.09, 0.07],
             "symbol": "✓", "conf": 0.94},
            {"block_type": "correction", "ink_role": "correction", "bbox": [0.09, 0.47, 0.82, 0.08],
             "text": "Area = 1/2 x 5 x 12 = 30", "color": BLUE, "size": 34, "hand": True, "conf": 0.85},
        ],
    },
]

PROBLEMS = [
    {
        "stem_latex": "x^2-5x+6=0",
        "refs": [[1, 0], [1, 1], [1, 2], [1, 3], [1, 4], [1, 5]],
        "knowledge": ["一元二次方程"],
        "method": ["因式分解法"],
    },
    {
        "stem_latex": "2x^2+3x-2=0",
        "refs": [[2, 0], [2, 1], [2, 2]],
        "knowledge": ["一元二次方程"],
        "method": ["公式法"],
    },
    {
        "stem_latex": r"AB=5,\ AC=12,\ \angle A=90^\circ",
        "refs": [[2, 3], [3, 0], [3, 1], [3, 2], [3, 3], [3, 4]],
        "knowledge": ["勾股定理", "三角形面积"],
        "method": ["数形结合"],
    },
]

OCR = {
    "stem": ["x^2-5x+6=0", 0.91],
    "answer": ["x=2 \\text{ or } x=3", 0.84],
    "correction": ["(x-2)(x-3)=0", 0.82],
    "mark": ["✗", 0.92],
}


def load_font(size: int, candidates: list[str], fallback: ImageFont.FreeTypeFont | None = None):
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    if fallback is not None:
        return fallback
    try:
        return ImageFont.load_default(size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def draw_text(draw: ImageDraw.ImageDraw, bbox, text, color, size, hand=False, mono=False):
    candidates = HAND_FONTS if hand else (MONO_FONTS if mono else SANS_FONTS)
    font = load_font(size, candidates)
    x = int(bbox[0] * W)
    y = int(bbox[1] * H)
    draw.text((x, y), text, fill=color, font=font)


def draw_mark(draw: ImageDraw.ImageDraw, bbox, symbol: str):
    x, y, w, h = bbox
    left, top = int(x * W), int(y * H)
    right, bottom = int((x + w) * W), int((y + h) * H)
    if symbol == "✓":
        draw.line([(left, top + (bottom - top) // 2),
                   (left + (right - left) // 3, bottom),
                   (right, top)], fill=RED, width=7)
    else:
        draw.line([(left, top), (right, bottom)], fill=RED, width=7)
        draw.line([(right, top), (left, bottom)], fill=RED, width=7)


def draw_axes(draw: ImageDraw.ImageDraw, bbox):
    x, y, w, h = bbox
    left, top = int(x * W), int(y * H)
    right, bottom = int((x + w) * W), int((y + h) * H)
    mid_y = (top + bottom) // 2
    mid_x = (left + right) // 2
    draw.line([(left, mid_y), (right, mid_y)], fill="#555", width=2)
    draw.line([(mid_x, top), (mid_x, bottom)], fill="#555", width=2)
    points = []
    for i in range(60):
        t = i / 59.0
        px = left + t * (right - left)
        norm = (t - 0.5) * 2
        py = mid_y - (norm * norm - 0.8) * (h * 0.45)
        points.append((px, max(top, min(bottom, py))))
    draw.line(points, fill=BLUE, width=3)


def draw_triangle(draw: ImageDraw.ImageDraw, bbox):
    x, y, w, h = bbox
    left, top = int(x * W), int(y * H)
    right, bottom = int((x + w) * W), int((y + h) * H)
    a = (left, bottom)
    b = (right, bottom)
    c = (right, int(top + (bottom - top) * 0.15))
    draw.line([a, b, c, a], fill="#333", width=3)
    draw.rectangle([right - 16, bottom - 16, right, bottom], outline="#333", width=2)
    font = load_font(22, SANS_FONTS)
    draw.text((a[0] - 22, a[1] - 24), "A", fill="#333", font=font)
    draw.text((b[0] + 4, b[1] - 24), "B", fill="#333", font=font)
    draw.text((c[0] + 4, c[1] - 26), "C", fill="#333", font=font)


def render_page(spec: dict) -> Image.Image:
    img = Image.new("RGB", (W, H), "#fdfcf9")
    draw = ImageDraw.Draw(img)
    for gy in range(140, H, 56):
        draw.line([(60, gy), (W - 60, gy)], fill="#eeeae2", width=1)

    header_font = load_font(24, SANS_FONTS)
    draw.text((70, 58), "Name: __________     Date: 2026-03-__", fill="#777", font=header_font)
    draw.text((W - 150, 58), f"p.{spec['idx']}", fill="#777", font=header_font)
    draw.line([(60, 100), (W - 60, 100)], fill="#999", width=2)

    for region in spec["regions"]:
        if "draw" in region:
            if region["draw"] == "axes":
                draw_axes(draw, region["bbox"])
            else:
                draw_triangle(draw, region["bbox"])
        elif "symbol" in region:
            draw_mark(draw, region["bbox"], region["symbol"])
        else:
            draw_text(
                draw,
                region["bbox"],
                region.get("text", ""),
                region.get("color", INK),
                region.get("size", 32),
                hand=region.get("hand", False),
            )
    return img


def build_canned() -> dict:
    pages = []
    for spec in PAGE_SPECS:
        regions = []
        for i, region in enumerate(spec["regions"]):
            regions.append(
                {
                    "block_type": region["block_type"],
                    "ink_role": region["ink_role"],
                    "bbox": region["bbox"],
                    "confidence": region.get("conf", 0.8),
                    "text": region.get("symbol", region.get("text", "")),
                    "order_idx": i,
                    "page_start": region.get("page_start", spec["idx"]),
                    "page_end": region.get("page_end", spec["idx"]),
                }
            )
        pages.append({"idx": spec["idx"], "regions": regions})
    return {"pages": pages, "problems": PROBLEMS, "ocr": OCR}


def main() -> None:
    FIXTURE_DEMO_DIR.mkdir(parents=True, exist_ok=True)
    for spec in PAGE_SPECS:
        out = FIXTURE_DEMO_DIR / f"p{spec['idx']}.jpg"
        render_page(spec).save(out, format="JPEG", quality=85)
        print(f"wrote {out.relative_to(REPO)}")
    CANNED_PATH.write_text(
        json.dumps(build_canned(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {CANNED_PATH.relative_to(REPO)}")


if __name__ == "__main__":
    main()
