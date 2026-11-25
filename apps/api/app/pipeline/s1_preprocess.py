"""s1 预处理：长边缩放（幂等）、灰度、自适应二值化、按需旋转矫正、debug 落盘。

长边 2000px 已在 storage.save_page 做过，这里再兜底一次以防外部直接落盘的原图。
倾斜角用墨迹点集的最小外接矩形估计：|angle| ∈ (1°, 15°] 自动转正并写回 page.image_path；
超过 15° 视为需要人工纠偏，只记录 page.rotation 并在 warnings 里提示，不做旋转。

已知限制：弱光/阴影下自适应二值化会产生噪点；旋转后 bbox 坐标系随之改变（原型接受）。
"""

from __future__ import annotations

import cv2
import numpy as np

from ..config import DEBUG_DIR, MAX_EDGE
from ..models import Page
from .base import StageContext, StageResult, ok_result

MAX_AUTO_ROTATE = 15.0  # 超过此角度不自动转，避免把整页转坏


def _deskew_angle(gray: np.ndarray) -> float:
    """用最小外接矩形估计倾斜角，返回需要旋转的补偿角（度，逆时针为正）。"""
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 15
    )
    points = cv2.findNonZero(binary)
    if points is None or len(points) < 50:
        return 0.0
    angle = float(cv2.minAreaRect(points)[-1])
    if angle > 45.0:
        angle -= 90.0
    elif angle < -45.0:
        angle += 90.0
    return angle


def _rotate(image: np.ndarray, angle: float) -> np.ndarray:
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_w = int(height * sin + width * cos)
    new_h = int(height * cos + width * sin)
    matrix[0, 2] += new_w / 2.0 - width / 2.0
    matrix[1, 2] += new_h / 2.0 - height / 2.0
    return cv2.warpAffine(
        image, matrix, (new_w, new_h), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255)
    )


class PreprocessStage:
    name = "preprocess"

    def run(self, ctx: StageContext) -> StageResult:
        page = ctx.session.get(Page, ctx.page_id)
        if page is None:
            return StageResult(ok=False, warnings=["page not found"], stats={})

        raw = ctx.storage.read(page.image_path)
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            page.status = "failed"
            ctx.session.commit()
            return StageResult(ok=False, warnings=["image decode failed"], stats={})

        warnings: list[str] = []
        height, width = image.shape[:2]
        longest = max(height, width)
        if longest > MAX_EDGE:
            ratio = MAX_EDGE / float(longest)
            image = cv2.resize(
                image, (int(width * ratio), int(height * ratio)), interpolation=cv2.INTER_AREA
            )
            height, width = image.shape[:2]

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        angle = _deskew_angle(gray)
        rotation = round(angle, 2) if abs(angle) > 1.0 else 0.0
        deskewed = False
        if abs(angle) > MAX_AUTO_ROTATE:
            warnings.append(f"skew {angle:.1f}deg exceeds {MAX_AUTO_ROTATE}deg, manual fix needed")
        elif abs(angle) > 1.0:
            image = _rotate(image, angle)
            deskewed = True
            height, width = image.shape[:2]
            ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 88])
            if ok:
                ctx.storage.abs(page.image_path).write_bytes(encoded.tobytes())

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 15
        )

        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(DEBUG_DIR / f"p{page.idx}_pre.png"), binary)

        page.width = width
        page.height = height
        page.rotation = rotation
        page.status = "ready"
        ctx.session.commit()

        stats = {
            "page_idx": page.idx,
            "width": width,
            "height": height,
            "rotation": rotation,
            "deskewed": deskewed,
            "ink_ratio": round(float((binary > 0).mean()), 4),
        }
        return StageResult(ok=True, warnings=warnings, stats=stats)


STAGE = PreprocessStage()
