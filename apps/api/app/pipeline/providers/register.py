"""按配置选择 provider，缺省一律回落到 mock（演示永不因缺模型而中断）。

OCR 配置来自 ai_config.effective()：数据库页面保存值 > 环境变量 > 默认值，
每次创建 provider 时重新解析，因此页面保存后下一个任务立即生效。
"""

from __future__ import annotations

import logging
import os

from sqlalchemy.orm import Session

from ...ai_config import effective as effective_ai_config
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


def get_chat_provider(session: Session | None = None):
    """打标用的 LLM provider；未配置 Key 时返回 None，打标自动走本地词表。"""
    cfg = effective_ai_config(session)
    if not cfg["api_key"]:
        return None
    try:
        from .chat import ChatProvider

        return ChatProvider(api_key=cfg["api_key"], base_url=cfg["base_url"], model=cfg["model"])
    except Exception as exc:  # pragma: no cover - 配置异常时降级
        logger.warning("chat provider unavailable (%s), fallback to local tagger", exc)
        return None


def get_ocr_provider(session: Session | None = None) -> OcrProvider:
    cfg = effective_ai_config(session)
    if cfg["provider"] == "vlm" and cfg["api_key"]:
        try:
            from .vlm import VlmOcrProvider

            return VlmOcrProvider(
                api_key=cfg["api_key"], base_url=cfg["base_url"], model=cfg["model"]
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("vlm ocr provider unavailable (%s), fallback to mock", exc)
    return MockOcrProvider()
