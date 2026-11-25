"""按环境变量选择 provider，缺省一律回落到 mock（演示永不因缺模型而中断）。"""

from __future__ import annotations

import logging
import os

from .base import LayoutProvider, OcrProvider
from .mock import MockLayoutProvider, MockOcrProvider

logger = logging.getLogger(__name__)


def get_layout_provider() -> LayoutProvider:
    mode = os.environ.get("LAYOUT_PROVIDER", "mock").lower()
    if mode == "opencv":
        try:
            from .opencv import OpenCvLayoutProvider

            return OpenCvLayoutProvider()
        except Exception as exc:  # pragma: no cover - 真实实现缺失时降级
            logger.warning("opencv layout provider unavailable (%s), fallback to mock", exc)
    return MockLayoutProvider()


def get_ocr_provider() -> OcrProvider:
    mode = os.environ.get("OCR_PROVIDER", "mock").lower()
    if mode == "vlm" and os.environ.get("VLM_API_KEY"):
        try:
            from .vlm import VlmOcrProvider

            return VlmOcrProvider()
        except Exception as exc:  # pragma: no cover
            logger.warning("vlm ocr provider unavailable (%s), fallback to mock", exc)
    return MockOcrProvider()
