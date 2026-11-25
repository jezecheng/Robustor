"""s3 墨迹分色：按 ink_profile.rules_json 做 HSV 分色，区分印刷 / 学生笔迹 / 批改 / 订正。

判定优先级：
1. 红/蓝色像素占比高 → 取规则里 color=red/blue 的 role（默认 mark / correction）；
2. 灰度近黑 → 用「连通域密度 + 墨迹密度」区分手写（answer）与印刷（print）；
3. figure / noise 保留结构先验（图示里的蓝色曲线不算订正）；
4. 其余或彩色但不在规则内 → ignore。

没有 rules_json 时回落到按 block_type 的默认映射；provider（如 mock）已给出 ink_role 的
予以保留，只有主色与已有角色明显冲突（同一块既判红又标成蓝色角色）时才覆盖。

已知限制：低饱和的彩色笔迹、偏色照片、彩纸背景会让主色判定漂移，阈值需要 WP7 的 UI 调。
"""

from __future__ import annotations

import cv2
import numpy as np
from sqlalchemy.orm import Session

from ..models import Page, Region
from .base import StageContext, StageResult, ok_result

DEFAULT_ROLE = {
    "stem": "print",
    "figure": "print",
    "answer": "answer",
    "mark": "mark",
    "correction": "correction",
    "noise": "ignore",
}

DEFAULT_RULES = {
    "roles": [
        {"role": "print", "color": "black", "mode": "printed", "sat_max": 40},
        {"role": "answer", "color": "black", "mode": "handwritten", "sat_max": 40},
        {"role": "mark", "color": "red", "hue": [-15, 20], "sat_min": 80},
        {"role": "correction", "color": "blue", "hue": [200, 255], "sat_min": 70},
    ]
}

FAMILY = {
    "mark": "red",
    "correction": "blue",
    "print": "black",
    "answer": "black",
    "ignore": "none",
}

COLOR_DOMINANT = 0.5  # 主色像素占墨迹的比例
OVERRIDE_STRENGTH = 0.6  # provider 已有角色时，仅主色非常明确才覆盖
INK_GRAY_MAX = 190
HAND_COMP_RATE = 30.0
HAND_INK_RATIO = 0.26


def _active_roles(rules: dict, page_idx: int | None) -> list[dict]:
    roles = [r for r in (rules.get("roles") or []) if isinstance(r, dict) and r.get("role")]
    if page_idx is not None:
        override = (rules.get("page_overrides") or {}).get(str(page_idx))
        if isinstance(override, dict) and "roles" in override:
            roles = [r for r in override["roles"] if isinstance(r, dict) and r.get("role")]
    return roles


def _role_for(roles: list[dict], color: str) -> str | None:
    for rule in roles:
        if rule.get("color") == color:
            return str(rule["role"])
    return None


def _hue_segments(rule: dict) -> list[tuple[int, int]]:
    """rules_json 的 hue 用角度 0–360，OpenCV 的 H 是 0–179，这里做换算与跨 0 拆分。"""
    hue = rule.get("hue") or [0, 0]
    lo = int(round(float(hue[0]) / 2.0)) % 180
    hi = int(round(float(hue[1]) / 2.0)) % 180
    if lo <= hi:
        return [(lo, hi)]
    return [(0, hi), (lo, 179)]


def _crop_box(bbox: list[float], width: int, height: int) -> tuple[int, int, int, int]:
    x, y, w, h = (float(v) for v in bbox)
    left = max(0, min(width - 1, int(round(x * width))))
    top = max(0, min(height - 1, int(round(y * height))))
    right = max(left + 1, min(width, int(round((x + w) * width))))
    bottom = max(top + 1, min(height, int(round((y + h) * height))))
    return left, top, right, bottom


def _ink_mask(crop_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    mask = (gray < INK_GRAY_MAX).astype(np.uint8)
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


def _color_fraction(hsv: np.ndarray, rule: dict, ink: np.ndarray) -> float:
    total = int(ink.sum())
    if total == 0:
        return 0.0
    hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    sat_min = float(rule.get("sat_min", 60))
    matched = np.zeros(ink.shape, dtype=bool)
    for lo, hi in _hue_segments(rule):
        matched |= (hue >= lo) & (hue <= hi) & (sat >= sat_min) & (val >= 40)
    return float((matched & ink.astype(bool)).sum()) / total


def _handwritten(mask: np.ndarray) -> bool:
    h, w = mask.shape
    if h == 0 or w == 0:
        return False
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
    glyphs = [s for s in stats[1:] if s[4] >= 20 and s[3] >= 0.35 * h]
    comp_rate = len(glyphs) / (w / 1000.0)
    ink_ratio = float(mask.sum()) / float(w * h)
    return comp_rate < HAND_COMP_RATE and ink_ratio < HAND_INK_RATIO


def _infer_detailed(
    image_bgr: np.ndarray,
    bbox: list[float],
    rules_json: dict | None = None,
    block_type: str | None = None,
    page_idx: int | None = None,
) -> tuple[str, float, str]:
    """返回 (ink_role, 主色置信度, 颜色族)。"""
    rules = rules_json if isinstance(rules_json, dict) and rules_json.get("roles") else DEFAULT_RULES
    roles = _active_roles(rules, page_idx)
    print_role = _role_for(roles, "black") or "print"

    if block_type == "noise":
        return "ignore", 0.0, "none"
    if block_type == "figure":
        return print_role, 0.0, "none"

    height, width = image_bgr.shape[:2]
    left, top, right, bottom = _crop_box(bbox, width, height)
    crop = image_bgr[top:bottom, left:right]
    mask = _ink_mask(crop)
    if int(mask.sum()) < 20:
        return "ignore", 0.0, "none"

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    ink = mask.astype(bool)

    red_rule = next((r for r in roles if r.get("color") == "red"), None)
    blue_rule = next((r for r in roles if r.get("color") == "blue"), None)
    red_frac = _color_fraction(hsv, red_rule, mask) if red_rule else 0.0
    blue_frac = _color_fraction(hsv, blue_rule, mask) if blue_rule else 0.0

    if red_rule and red_frac >= COLOR_DOMINANT and red_frac >= blue_frac:
        return _role_for(roles, "red") or "mark", red_frac, "red"
    if blue_rule and blue_frac >= COLOR_DOMINANT:
        return _role_for(roles, "blue") or "correction", blue_frac, "blue"

    black_rule = next(
        (r for r in roles if r.get("color") == "black" and r.get("mode") == "handwritten"),
        None,
    )
    sat_min = float((black_rule or {}).get("sat_min", 40))
    sat_frac = float((hsv[:, :, 1][ink] >= sat_min).mean()) if ink.any() else 0.0
    if sat_frac >= 0.5:  # 彩色但不属于规则里的红/蓝
        return "ignore", 0.0, "none"

    if _handwritten(mask):
        return (str(black_rule["role"]) if black_rule else "answer"), 0.0, "black"
    return print_role, 0.0, "black"


def infer_ink_role(
    image_bgr: np.ndarray,
    bbox: list[float],
    rules_json: dict | None = None,
    block_type: str | None = None,
    page_idx: int | None = None,
) -> str:
    """单个 region 的主色 → ink_role（供 s3 与测试复用）。"""
    return _infer_detailed(image_bgr, bbox, rules_json, block_type, page_idx)[0]


def _should_override(existing: str, inferred: str, family: str, strength: float) -> bool:
    if existing == inferred:
        return False
    if family in ("red", "blue") and strength >= OVERRIDE_STRENGTH:
        return FAMILY.get(existing) != family
    return False


class InkStage:
    name = "ink"

    def run(self, ctx: StageContext) -> StageResult:
        page = ctx.session.get(Page, ctx.page_id)
        if page is None:
            return StageResult(ok=False, warnings=["page not found"], stats={})

        regions = ctx.session.query(Region).filter(Region.page_id == page.id).all()
        rules = ctx.config.get("ink_profile") or {}
        roles = _active_roles(rules, page.idx)

        image = None
        if roles and regions:
            raw = ctx.storage.read(page.image_path)
            image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)

        assigned = kept = overridden = 0
        for region in regions:
            if not roles or image is None:
                if not region.ink_role:
                    region.ink_role = DEFAULT_ROLE.get(region.block_type, "ignore")
                    assigned += 1
                continue

            inferred, strength, family = _infer_detailed(
                image, list(region.bbox), rules, region.block_type, page.idx
            )
            if not region.ink_role:
                region.ink_role = inferred
                assigned += 1
            elif _should_override(region.ink_role, inferred, family, strength):
                region.ink_role = inferred
                overridden += 1
            else:
                kept += 1

        ctx.session.commit()

        counts: dict[str, int] = {}
        for region in regions:
            key = region.ink_role or "unknown"
            counts[key] = counts.get(key, 0) + 1
        return ok_result(
            regions=len(regions),
            assigned=assigned,
            kept=kept,
            overridden=overridden,
            roles=counts,
            has_rules=bool(roles),
        )


STAGE = InkStage()
