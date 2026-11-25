"""OpenCV 版面检测 provider：投影法切行 + 行内连通域合并 + 颜色/形状启发式打 block_type。

流程：自适应二值化取墨迹（再用灰度阈值滤掉浅色横线）→ 水平投影找行带 →
行带内横向闭运算把字符合并成块 → 逐块按 HSV 判红/蓝、按长直线/闭合轮廓判 figure、
按「连通域密度 + 墨迹密度」区分黑笔手写与印刷体。

已知限制（原型阶段刻意接受）：
- 只保证 fixture 这类浅底、近似正射的扫描/拍照；倾斜 >5° 需人工纠偏；
- 弱光、阴影、彩色纸底会让 HSV 判色与黑笔手写判定失效；
- figure 只识别「轴对齐长直线」或「大面积闭合轮廓」，散点图等会漏判。
"""

from __future__ import annotations

import cv2
import numpy as np

from ...config import DEBUG_DIR
from .base import RegionCandidate

# 调试图颜色（BGR）
BLOCK_COLORS = {
    "stem": (60, 160, 60),
    "figure": (200, 90, 180),
    "answer": (30, 140, 230),
    "mark": (40, 40, 220),
    "correction": (220, 120, 30),
    "noise": (140, 140, 140),
}

# 度数 → OpenCV hue（0–179）
RED_HUE = (172, 179)
BLUE_HUE = (100, 132)
COLOR_SAT_MIN = 70
COLOR_VAL_MIN = 40

HAND_COMP_RATE = 30.0  # 每个 1000px 宽度内的连通域个数，手写显著更少
HAND_INK_RATIO = 0.26  # 墨迹像素 / 块面积，手写更稀疏


def _ink_mask(gray: np.ndarray) -> np.ndarray:
    """自适应二值化 + 绝对灰度阈值，过滤 #eee 级别的横线/纸纹。"""
    adaptive = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 15
    )
    dark = (gray < 180).astype(np.uint8) * 255
    mask = cv2.bitwise_and(adaptive, dark)
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


def _row_bands(mask: np.ndarray) -> list[tuple[int, int]]:
    """水平投影切行：有墨迹的行合并为行带，丢弃过矮/过空的带。"""
    height, width = mask.shape
    proj = (mask > 0).sum(axis=1)
    threshold = max(2, int(round(0.0012 * width)))
    active = proj >= threshold

    raw: list[list[int]] = []
    y = 0
    while y < height:
        if active[y]:
            start = y
            while y < height and active[y]:
                y += 1
            raw.append([start, y])
        else:
            y += 1

    gap = max(4, int(round(0.004 * height)))
    merged: list[list[int]] = []
    for start, end in raw:
        if merged and start - merged[-1][1] <= gap:
            merged[-1][1] = end
        else:
            merged.append([start, end])

    min_ink = 0.00025 * width * height
    return [
        (start, end)
        for start, end in merged
        if end - start >= 6 and float((mask[start:end] > 0).sum()) >= min_ink
    ]


def _band_blocks(mask: np.ndarray, y0: int, y1: int) -> list[tuple[int, int, int, int]]:
    """行带内横向闭运算把字符/单词连成块，返回像素 bbox。"""
    band = mask[y0:y1]
    height, width = mask.shape
    band_h = y1 - y0
    kernel_w = int(np.clip(1.6 * band_h, 11, 61))
    closed = cv2.morphologyEx(band, cv2.MORPH_CLOSE, np.ones((3, kernel_w), np.uint8))

    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(closed, 8)
    min_area = max(40, int(0.0001 * width * height))
    blocks: list[tuple[int, int, int, int]] = []
    for i in range(1, count):
        x, y, w, h, area = (int(v) for v in stats[i])
        if area < min_area or w < 8 or h < 6:
            continue
        blocks.append((x, y0 + y, w, h))
    return blocks


def _color_fractions(crop_bgr: np.ndarray, crop_mask: np.ndarray) -> tuple[float, float]:
    """返回 (红像素占比, 蓝像素占比)，分母为墨迹像素。"""
    ink = int((crop_mask > 0).sum())
    if ink == 0:
        return 0.0, 0.0
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    colored = (sat >= COLOR_SAT_MIN) & (val >= COLOR_VAL_MIN)
    red = (colored & ((hue <= 10) | (hue >= RED_HUE[0]))).sum()
    blue = (colored & (hue >= BLUE_HUE[0]) & (hue <= BLUE_HUE[1])).sum()
    return float(red) / ink, float(blue) / ink


def _is_figure(crop_mask: np.ndarray, page_area: float) -> tuple[bool, float]:
    """轴对齐长直线（坐标轴）或大面积闭合轮廓（三角形/圆）判为图示。"""
    h, w = crop_mask.shape
    if w < 24 or h < 24:
        return False, 0.0

    row_max = float((crop_mask > 0).sum(axis=1).max()) / w
    col_max = float((crop_mask > 0).sum(axis=0).max()) / h
    if row_max >= 0.65 and col_max >= 0.55:
        return True, 0.9

    contours, _ = cv2.findContours(crop_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    largest = max((cv2.contourArea(c) for c in contours), default=0.0)
    if largest >= 0.0012 * page_area:
        return True, 0.8
    return False, 0.0


def _text_stats(crop_mask: np.ndarray) -> tuple[bool, dict]:
    """黑/灰墨迹的手写判定：连通域密度低 + 墨迹密度低 → 手写。"""
    h, w = crop_mask.shape
    ink = int((crop_mask > 0).sum())
    if ink == 0 or w == 0 or h == 0:
        return False, {"comp_rate": 0.0, "ink_ratio": 0.0}

    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(crop_mask, 8)
    glyphs = [s for s in stats[1:] if s[4] >= 20 and s[3] >= 0.35 * h]
    comp_rate = len(glyphs) / (w / 1000.0)
    ink_ratio = ink / float(w * h)
    handwritten = comp_rate < HAND_COMP_RATE and ink_ratio < HAND_INK_RATIO
    return handwritten, {"comp_rate": round(comp_rate, 1), "ink_ratio": round(ink_ratio, 3)}


def _classify(
    crop_bgr: np.ndarray,
    crop_mask: np.ndarray,
    page_area: float,
) -> tuple[str, float]:
    red_frac, blue_frac = _color_fractions(crop_bgr, crop_mask)
    # 阈值取 0.8：批改/订正区域的彩色像素占比接近 1，而图示里的蓝色曲线只占 ~0.7
    if red_frac >= 0.8:
        return "mark", round(min(0.98, 0.6 + 0.35 * red_frac), 3)
    if blue_frac >= 0.8:
        return "correction", round(min(0.98, 0.6 + 0.35 * blue_frac), 3)

    is_fig, fig_conf = _is_figure(crop_mask, page_area)
    if is_fig:
        return "figure", fig_conf

    handwritten, metrics = _text_stats(crop_mask)
    if handwritten:
        conf = 0.55 + max(0.0, (HAND_COMP_RATE - metrics["comp_rate"]) / 60.0)
        return "answer", round(min(0.95, conf), 3)
    return "stem", 0.85


def _draw_overlay(image: np.ndarray, regions: list[RegionCandidate], page_idx: int) -> None:
    """调试图落盘，便于肉眼核对 5 类颜色框。"""
    canvas = image.copy()
    height, width = canvas.shape[:2]
    for item in regions:
        x, y, w, h = item["bbox"]
        left, top = int(x * width), int(y * height)
        right, bottom = int((x + w) * width), int((y + h) * height)
        color = BLOCK_COLORS.get(str(item["block_type"]), (140, 140, 140))
        cv2.rectangle(canvas, (left, top), (right, bottom), color, 2)
        cv2.putText(
            canvas, f"{item['block_type']} {item['confidence']:.2f}",
            (left + 2, max(14, top - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA,
        )
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(DEBUG_DIR / f"p{page_idx}_overlay.png"), canvas)


class OpenCvLayoutProvider:
    name = "opencv"

    def detect(self, image_bytes: bytes, page_idx: int, cfg: dict) -> list[RegionCandidate]:
        data = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if image is None:
            return []

        height, width = image.shape[:2]
        max_edge = int(cfg.get("max_edge", 2000) or 2000)
        longest = max(height, width)
        if longest > max_edge:
            ratio = max_edge / float(longest)
            size = (int(width * ratio), int(height * ratio))
            image = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
            height, width = image.shape[:2]

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        mask = _ink_mask(gray)
        page_area = float(width * height)

        boxes: list[tuple[int, int, int, int]] = []
        for y0, y1 in _row_bands(mask):
            boxes.extend(_band_blocks(mask, y0, y1))

        # 阅读顺序：行带自上而下已有序，行内按 x
        boxes.sort(key=lambda b: (b[1], b[0]))

        regions: list[RegionCandidate] = []
        for x, y, w, h in boxes:
            if y + h <= 0.06 * height:  # 页眉（Name/Date/页码）
                continue
            if w < 0.006 * width or h < 0.005 * height:
                continue
            nx, ny = min(max(x / width, 0.0), 1.0), min(max(y / height, 0.0), 1.0)
            bbox = [round(nx, 6), round(ny, 6),
                    round(min(w / width, 1.0 - nx), 6), round(min(h / height, 1.0 - ny), 6)]
            if bbox[2] <= 0 or bbox[3] <= 0:
                continue

            crop = image[y : y + h, x : x + w]
            crop_mask = mask[y : y + h, x : x + w]
            block_type, confidence = _classify(crop, crop_mask, page_area)
            regions.append(
                {
                    "block_type": block_type,
                    "ink_role": None,
                    "bbox": bbox,
                    "confidence": max(0.0, min(1.0, confidence)),
                    "text": "",
                    "order_idx": len(regions),
                    "page_start": page_idx,
                    "page_end": page_idx,
                }
            )

        _draw_overlay(image, regions, page_idx)
        return regions
