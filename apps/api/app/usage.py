"""AI 用量落库：把 OpenAI 兼容响应的 usage 拆成输入/输出/推理/缓存四类。

记录失败绝不阻断主流程：AI 请求本身的异常由 provider 转成 RuntimeError 交由阶段降级，
这里只负责尽力写一条日志。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from .models import AiUsageLog

logger = logging.getLogger(__name__)


def _count(value: Any) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return max(0, number)


def usage_counts(usage: dict | None) -> dict[str, int]:
    """解析 usage；兼容 OpenAI / DeepSeek / 部分中转的字段命名差异。"""
    empty = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "reasoning_tokens": 0,
        "cached_tokens": 0,
        "total_tokens": 0,
    }
    if not isinstance(usage, dict):
        return empty

    prompt = _count(usage.get("prompt_tokens", usage.get("input_tokens")))
    completion = _count(usage.get("completion_tokens", usage.get("output_tokens")))

    out_details = usage.get("completion_tokens_details") or usage.get("output_tokens_details") or {}
    reasoning = 0
    if isinstance(out_details, dict):
        reasoning = _count(out_details.get("reasoning_tokens"))
    if not reasoning:
        reasoning = _count(usage.get("reasoning_tokens"))

    in_details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
    cached = 0
    if isinstance(in_details, dict):
        cached = _count(in_details.get("cached_tokens"))
        if not cached:
            cached = _count(in_details.get("cache_read_input_tokens"))
    if not cached:
        cached = _count(
            usage.get("prompt_cache_hit_tokens")
            or usage.get("cache_read_input_tokens")
            or usage.get("cached_tokens")
        )

    # 推理属于输出、缓存命中属于输入：裁剪到上限，避免图表出现超过总量的分段。
    reasoning = min(reasoning, completion)
    cached = min(cached, prompt)

    total = _count(usage.get("total_tokens")) or prompt + completion
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "reasoning_tokens": reasoning,
        "cached_tokens": cached,
        "total_tokens": total,
    }


def record_ai_usage(
    session: Session | None,
    *,
    scene: str,
    provider_name: str,
    model: str,
    success: bool,
    provider_id: str | None = None,
    document_id: str | None = None,
    latency_ms: int = 0,
    error: str | None = None,
    usage: dict | None = None,
) -> None:
    """写一条用量日志。session 为空（无 DB 场景）时直接跳过。"""
    if session is None:
        return
    counts = usage_counts(usage)
    try:
        session.add(
            AiUsageLog(
                scene=scene[:32],
                provider_id=provider_id,
                provider_name=(provider_name or "未命名配置")[:128],
                model=(model or "")[:128],
                document_id=document_id,
                success=success,
                error=(error or None) and str(error)[:500],
                latency_ms=max(0, int(latency_ms)),
                **counts,
            )
        )
        # 立即提交，保证阶段后续失败/回滚时这条请求记录仍然存在。
        session.commit()
    except Exception:  # noqa: BLE001 - 用量记录失败不影响业务
        logger.exception("failed to record ai usage")
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass
