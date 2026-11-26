"""AI 用量：按时间汇总 token，并分页列出每一次请求。

统计口径：
- 时间范围参数接受 ISO 8601（带时区会转成 UTC）；缺省为最近 7 天。
- 展示按东八区自然日/自然月分桶（服务端存的是朴素 UTC）。
- 「输入 / 输出」是总量，「缓存」是输入的一部分，「推理」是输出的一部分。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import AiUsageLog
from ..schemas import (
    AiUsageBucketOut,
    AiUsageFacetOut,
    AiUsageRequestListOut,
    AiUsageRequestOut,
    AiUsageSummaryOut,
    AiUsageTotalsOut,
)

router = APIRouter()

LOCAL_OFFSET = timedelta(hours=8)  # 东八区展示口径
DEFAULT_WINDOW_DAYS = 7
AUTO_MONTH_SPAN_DAYS = 92


def _parse_dt(value: str | None, fallback: datetime) -> datetime:
    if not value:
        return fallback
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"时间格式不正确：{value}") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _bucket_expr(bucket: Literal["day", "month"]):
    fmt = "%Y-%m-%d" if bucket == "day" else "%Y-%m"
    return func.strftime(fmt, AiUsageLog.created_at, "+8 hours")


def _bucket_labels(start: datetime, end: datetime, bucket: Literal["day", "month"]) -> list[str]:
    local_start = start + LOCAL_OFFSET
    local_end = end + LOCAL_OFFSET
    if bucket == "month":
        year, month = local_start.year, local_start.month
        labels: list[str] = []
        while (year, month) <= (local_end.year, local_end.month):
            labels.append(f"{year:04d}-{month:02d}")
            month += 1
            if month > 12:
                month = 1
                year += 1
        return labels

    labels = []
    day = local_start.date()
    last = local_end.date()
    while day <= last:
        labels.append(day.isoformat())
        day += timedelta(days=1)
    return labels


def _facet(
    session: Session, column, start: datetime, end: datetime
) -> list[AiUsageFacetOut]:
    requests = func.count(AiUsageLog.id)
    tokens = func.sum(AiUsageLog.total_tokens)
    rows = (
        session.query(column, requests, tokens)
        .filter(AiUsageLog.created_at >= start, AiUsageLog.created_at <= end)
        .group_by(column)
        .order_by(requests.desc())
        .all()
    )
    return [
        AiUsageFacetOut(
            value=str(value) if value else "未记录",
            requests=int(count or 0),
            total_tokens=int(token_sum or 0),
        )
        for value, count, token_sum in rows
    ]


@router.get("/ai-usage/summary", response_model=AiUsageSummaryOut)
def ai_usage_summary(
    start: str | None = None,
    end: str | None = None,
    bucket: Literal["day", "month"] | None = None,
    session: Session = Depends(get_session),
) -> AiUsageSummaryOut:
    end_dt = _parse_dt(end, datetime.utcnow())
    start_dt = _parse_dt(start, end_dt - timedelta(days=DEFAULT_WINDOW_DAYS - 1))
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt

    if bucket is None:
        bucket = (
            "month"
            if (end_dt - start_dt) > timedelta(days=AUTO_MONTH_SPAN_DAYS)
            else "day"
        )

    base_filter = (AiUsageLog.created_at >= start_dt, AiUsageLog.created_at <= end_dt)

    totals_row = (
        session.query(
            func.count(AiUsageLog.id),
            func.sum(case((AiUsageLog.success.is_(True), 1), else_=0)),
            func.sum(case((AiUsageLog.success.is_(False), 1), else_=0)),
            func.sum(AiUsageLog.prompt_tokens),
            func.sum(AiUsageLog.completion_tokens),
            func.sum(AiUsageLog.reasoning_tokens),
            func.sum(AiUsageLog.cached_tokens),
            func.sum(AiUsageLog.total_tokens),
            func.avg(AiUsageLog.latency_ms),
        )
        .filter(*base_filter)
        .one()
    )
    requests = int(totals_row[0] or 0)
    success = int(totals_row[1] or 0)
    totals = AiUsageTotalsOut(
        requests=requests,
        success=success,
        failed=int(totals_row[2] or 0),
        success_rate=round(success / requests, 4) if requests else 0.0,
        prompt_tokens=int(totals_row[3] or 0),
        completion_tokens=int(totals_row[4] or 0),
        reasoning_tokens=int(totals_row[5] or 0),
        cached_tokens=int(totals_row[6] or 0),
        total_tokens=int(totals_row[7] or 0),
        avg_latency_ms=int(totals_row[8] or 0),
    )

    label = _bucket_expr(bucket)
    grouped = (
        session.query(
            label,
            func.count(AiUsageLog.id),
            func.sum(case((AiUsageLog.success.is_(True), 1), else_=0)),
            func.sum(case((AiUsageLog.success.is_(False), 1), else_=0)),
            func.sum(AiUsageLog.prompt_tokens),
            func.sum(AiUsageLog.completion_tokens),
            func.sum(AiUsageLog.reasoning_tokens),
            func.sum(AiUsageLog.cached_tokens),
            func.sum(AiUsageLog.total_tokens),
        )
        .filter(*base_filter)
        .group_by(label)
        .all()
    )
    by_bucket = {str(row[0]): row for row in grouped}

    series: list[AiUsageBucketOut] = []
    for value in _bucket_labels(start_dt, end_dt, bucket):
        row = by_bucket.get(value)
        bucket_requests = int(row[1] or 0) if row else 0
        bucket_success = int(row[2] or 0) if row else 0
        series.append(
            AiUsageBucketOut(
                bucket=value,
                requests=bucket_requests,
                success=bucket_success,
                failed=int(row[3] or 0) if row else 0,
                success_rate=round(bucket_success / bucket_requests, 4) if bucket_requests else 0.0,
                prompt_tokens=int(row[4] or 0) if row else 0,
                completion_tokens=int(row[5] or 0) if row else 0,
                reasoning_tokens=int(row[6] or 0) if row else 0,
                cached_tokens=int(row[7] or 0) if row else 0,
                total_tokens=int(row[8] or 0) if row else 0,
            )
        )

    return AiUsageSummaryOut(
        start=start_dt,
        end=end_dt,
        bucket=bucket,
        totals=totals,
        series=series,
        scenes=_facet(session, AiUsageLog.scene, start_dt, end_dt),
        providers=_facet(session, AiUsageLog.provider_name, start_dt, end_dt),
        models=_facet(session, AiUsageLog.model, start_dt, end_dt),
    )


@router.get("/ai-usage/requests", response_model=AiUsageRequestListOut)
def ai_usage_requests(
    start: str | None = None,
    end: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    success: bool | None = None,
    session: Session = Depends(get_session),
) -> AiUsageRequestListOut:
    end_dt = _parse_dt(end, datetime.utcnow())
    start_dt = _parse_dt(start, end_dt - timedelta(days=DEFAULT_WINDOW_DAYS - 1))
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt

    filters = [AiUsageLog.created_at >= start_dt, AiUsageLog.created_at <= end_dt]
    if success is not None:
        filters.append(AiUsageLog.success.is_(success))

    query = session.query(AiUsageLog).filter(*filters)
    total = query.count()
    rows = (
        query.order_by(AiUsageLog.created_at.desc(), AiUsageLog.id.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return AiUsageRequestListOut(
        items=[
            AiUsageRequestOut(
                id=row.id,
                created_at=row.created_at,
                scene=row.scene,
                success=row.success,
                provider_name=row.provider_name,
                model=row.model,
                document_id=row.document_id,
                latency_ms=row.latency_ms,
                error=row.error,
                prompt_tokens=row.prompt_tokens,
                completion_tokens=row.completion_tokens,
                reasoning_tokens=row.reasoning_tokens,
                cached_tokens=row.cached_tokens,
                total_tokens=row.total_tokens,
            )
            for row in rows
        ],
        total=total,
        page=page,
        size=size,
    )
