"""WP6 · 统计与复习调度。"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Problem, ProblemTag, Review, Tag, utcnow
from ..schemas import ReviewIn, ReviewOut, StatItem, StatsOverview

router = APIRouter(tags=["stats"])

MAX_EASE = 2.8
MIN_EASE = 1.3
DEFAULT_EASE = 2.5
DEFAULT_INTERVAL = 1


def _tag_counts(session: Session, tag_type: str) -> list[StatItem]:
    """按 problem_tag join tag 计数，只统计 approved，倒序取前 20。"""
    count = func.count(ProblemTag.problem_id)
    rows = (
        session.query(Tag.name, count)
        .join(ProblemTag, ProblemTag.tag_id == Tag.id)
        .join(Problem, Problem.id == ProblemTag.problem_id)
        .filter(Tag.type == tag_type, Tag.status == "approved", Problem.status == "confirmed")
        .group_by(Tag.id, Tag.name)
        .order_by(count.desc(), Tag.name)
        .limit(20)
        .all()
    )
    return [StatItem(name=name, count=total) for name, total in rows]


@router.get("/stats/overview", response_model=StatsOverview)
def stats_overview(session: Session = Depends(get_session)) -> StatsOverview:
    # 只统计已确认入库的题目（draft 属于流水线中间态，不进错题本与统计）。
    total = (
        session.query(func.count(Problem.id))
        .filter(Problem.status == "confirmed")
        .scalar()
        or 0
    )

    subject_count = func.count(Problem.id)
    subject_rows = (
        session.query(Problem.subject, subject_count)
        .filter(Problem.status == "confirmed")
        .group_by(Problem.subject)
        .order_by(subject_count.desc(), Problem.subject)
        .all()
    )

    # due 语义见 C.1-8：今日到期 = due_at <= 今日 23:59:59（含逾期）。
    end_of_day = datetime.combine(utcnow().date(), time(23, 59, 59))
    due_today = (
        session.query(func.count(func.distinct(Review.problem_id)))
        .join(Problem, Problem.id == Review.problem_id)
        .filter(Problem.status == "confirmed", Review.due_at <= end_of_day)
        .scalar()
        or 0
    )

    return StatsOverview(
        total=total,
        by_subject=[StatItem(name=name, count=count) for name, count in subject_rows],
        by_knowledge=_tag_counts(session, "knowledge"),
        by_method=_tag_counts(session, "method"),
        due_today=due_today,
    )


def _next_schedule(grade: int, ease: float, interval: int) -> tuple[float, int]:
    """简化 SM-2：0/1 重置为 1 天并降 ease；2 按 ease 推进；3 额外乘 1.2。"""
    if grade < 2:
        return max(MIN_EASE, ease - 0.2), 1
    if grade == 2:
        return ease, max(1, round(interval * ease))
    return ease, max(1, round(interval * ease * 1.2))


@router.post("/problems/{problem_id}/review", response_model=ReviewOut)
def review_problem(
    problem_id: str, payload: ReviewIn, session: Session = Depends(get_session)
) -> ReviewOut:
    problem = session.get(Problem, problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="题目不存在")

    review = session.query(Review).filter(Review.problem_id == problem.id).one_or_none()
    if review is None:
        review = Review(
            problem_id=problem.id,
            ease=DEFAULT_EASE,
            interval_days=DEFAULT_INTERVAL,
            due_at=utcnow(),
            history_json=[],
        )
        session.add(review)

    ease, interval = _next_schedule(int(payload.grade), float(review.ease), int(review.interval_days))
    ease = min(MAX_EASE, ease)
    now = utcnow()
    review.ease = ease
    review.interval_days = interval
    review.due_at = now + timedelta(days=interval)

    history: list[dict[str, Any]] = list(review.history_json or [])
    history.append({"grade": int(payload.grade), "at": now.isoformat(), "interval_days": interval})
    # JSON 列的原地 append 不会被 SQLAlchemy 追踪，必须整体赋值。
    review.history_json = history

    session.commit()
    session.refresh(review)
    return ReviewOut(
        problem_id=problem.id,
        ease=review.ease,
        interval_days=review.interval_days,
        due_at=review.due_at,
    )
