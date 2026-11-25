"""Provider 接口定义。真实实现放 providers/opencv.py（WP2）与 providers/vlm.py（WP3）。"""

from __future__ import annotations

from typing import Protocol, TypedDict, runtime_checkable


class RegionCandidate(TypedDict, total=False):
    block_type: str  # stem | figure | answer | mark | correction | noise
    ink_role: str | None
    bbox: list[float]  # 归一化 [x, y, w, h]
    confidence: float
    text: str  # mock 下直接带识别文本；真实实现留空由 s4 补
    order_idx: int
    page_start: int
    page_end: int


@runtime_checkable
class LayoutProvider(Protocol):
    name: str

    def detect(self, image_bytes: bytes, page_idx: int, cfg: dict) -> list[RegionCandidate]:
        """输入整页图片字节，输出候选块列表。不允许写库。"""
        ...


@runtime_checkable
class OcrProvider(Protocol):
    name: str

    def recognize(self, image_bytes: bytes, hint: str) -> tuple[str, float]:
        """返回 (latex_or_text, confidence 0–1)。"""
        ...
