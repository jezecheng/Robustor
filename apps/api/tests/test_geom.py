"""WP2 图像几何验收：对 fixtures/demo 三页直接跑 OpenCV provider 与 s3 的颜色判定。

断言：
1. 三页合计 ≥5 个 region，block_type 覆盖 ≥5 类；
2. 每个 bbox 四值都在 [0,1]，w/h > 0，x+w<=1、y+h<=1，confidence ∈ [0,1]；
3. 红/蓝 region 的 ink_role 判定为 mark / correction（黑笔、印刷、图示也一并核对）。
"""

from __future__ import annotations

from collections import Counter

import cv2
import pytest

from app.config import DEBUG_DIR, FIXTURE_DEMO_DIR
from app.pipeline.providers.opencv import OpenCvLayoutProvider
from app.pipeline.s3_ink import DEFAULT_RULES, infer_ink_role

PAGES = (1, 2, 3)
EXPECTED_ROLE = {
    "stem": "print",
    "figure": "print",
    "answer": "answer",
    "mark": "mark",
    "correction": "correction",
}


@pytest.fixture(scope="module")
def detected() -> dict[int, tuple[object, list[dict]]]:
    provider = OpenCvLayoutProvider()
    assert provider.name == "opencv"
    result: dict[int, tuple[object, list[dict]]] = {}
    for idx in PAGES:
        path = FIXTURE_DEMO_DIR / f"p{idx}.jpg"
        assert path.exists(), f"fixture missing: {path}"
        image = cv2.imread(str(path))
        result[idx] = (image, provider.detect(path.read_bytes(), idx, {}))
    return result


def test_layout_block_type_coverage(detected):
    blocks = [region for _image, regions in detected.values() for region in regions]
    types = Counter(region["block_type"] for region in blocks)
    print("\nblock_type 分布:", dict(types))
    for idx, (_image, regions) in detected.items():
        print(f"  p{idx}:", Counter(r["block_type"] for r in regions))

    assert len(blocks) >= 5
    assert len(types) >= 5
    assert {"stem", "figure", "answer", "mark", "correction"} <= set(types)


def test_bbox_normalized_and_confident(detected):
    for idx, (_image, regions) in detected.items():
        assert regions, f"page {idx} should produce regions"
        for region in regions:
            box = [float(v) for v in region["bbox"]]
            assert len(box) == 4
            x, y, w, h = box
            assert all(0.0 <= v <= 1.0 for v in box), f"bbox out of range: {box}"
            assert w > 0 and h > 0, f"degenerate bbox: {box}"
            assert x + w <= 1.0 + 1e-6, f"x+w>1: {box}"
            assert y + h <= 1.0 + 1e-6, f"y+h>1: {box}"
            assert 0.0 <= float(region["confidence"]) <= 1.0
            assert int(region["page_start"]) == idx
            assert int(region["page_end"]) == idx


def test_ink_roles_match_color(detected):
    checked = Counter()
    for idx, (image, regions) in detected.items():
        for region in regions:
            block_type = region["block_type"]
            role = infer_ink_role(
                image,
                region["bbox"],
                DEFAULT_RULES,
                block_type=block_type,
                page_idx=idx,
            )
            print(f"p{idx} {block_type:10s} role={role:10s} bbox={region['bbox']}")
            assert role == EXPECTED_ROLE[block_type], (idx, block_type, role)
            checked[block_type] += 1

    assert checked["mark"] >= 1, "fixture 里的红笔 ✗/✓ 未被识别"
    assert checked["correction"] >= 1, "fixture 里的蓝笔订正未被识别"


def test_debug_overlays_written(detected):
    for idx in detected:
        assert (DEBUG_DIR / f"p{idx}_overlay.png").exists(), "缺少 overlay 调试图"
