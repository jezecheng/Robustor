"""知识图谱：按学科浏览、节点详情、先修链、题目诊断路径。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Problem, ProblemTag, Tag, TagEdge
from ..schemas import (
    TaxonomyFacetOut,
    TaxonomyNeighborOut,
    TaxonomyPathOut,
    TaxonomySummaryOut,
    TaxonomyTopicBriefOut,
    TaxonomyTopicDetailOut,
    TaxonomyTopicOut,
)
from ..taxonomy import load_meta

router = APIRouter(tags=["taxonomy"])

MAX_DEPTH = 12


def _brief(tag: Tag) -> TaxonomyTopicBriefOut:
    return TaxonomyTopicBriefOut(
        id=tag.id,
        name=tag.name,
        subject=tag.subject,
        domain=tag.domain,
        grade=tag.grade,
        semester=tag.semester,
        chapter=tag.chapter,
        topic_type=tag.topic_type,
    )


def _topic(tag: Tag) -> TaxonomyTopicOut:
    return TaxonomyTopicOut(
        **_brief(tag).model_dump(),
        external_id=tag.external_id or "",
        description=tag.description or "",
        mastery_criteria=list(tag.mastery_json or []),
        diagnostic_question=tag.diagnostic_json or None,
        standards=list(tag.standards_json or []),
    )


def _neighbor(tag: Tag, edge: TagEdge) -> TaxonomyNeighborOut:
    return TaxonomyNeighborOut(
        **_brief(tag).model_dump(),
        strength=edge.strength,
        reason=edge.reason,
    )


def _order(tags: list[Tag]) -> list[Tag]:
    return sorted(tags, key=lambda tag: (tag.grade is None, tag.grade or 0, tag.chapter or "", tag.name))


def _ancestors(session: Session, start_ids: set[str], depth: int = MAX_DEPTH) -> list[Tag]:
    """沿 tag_edge 反向（前置方向）求传递闭包，防止环。"""
    seen = set(start_ids)
    frontier = set(start_ids)
    found: dict[str, Tag] = {}
    for _ in range(depth):
        if not frontier:
            break
        rows = (
            session.query(TagEdge, Tag)
            .join(Tag, Tag.id == TagEdge.from_tag_id)
            .filter(TagEdge.to_tag_id.in_(frontier))
            .all()
        )
        frontier = set()
        for _edge, tag in rows:
            if tag.id in seen:
                continue
            seen.add(tag.id)
            found[tag.id] = tag
            frontier.add(tag.id)
    return _order(list(found.values()))


@router.get("/taxonomy/summary", response_model=TaxonomySummaryOut)
def taxonomy_summary(session: Session = Depends(get_session)) -> TaxonomySummaryOut:
    meta = load_meta()
    base = session.query(Tag).filter(Tag.external_id.is_not(None))
    subjects = (
        base.with_entities(Tag.subject, func.count(Tag.id))
        .filter(Tag.subject.is_not(None))
        .group_by(Tag.subject)
        .all()
    )
    return TaxonomySummaryOut(
        topics=base.count(),
        edges=session.query(TagEdge).count(),
        subjects=[TaxonomyFacetOut(value=str(name), count=count) for name, count in subjects],
        source=str(meta.get("source") or ""),
        license=str(meta.get("license") or ""),
        commit=str(meta.get("commit") or ""),
    )


@router.get("/taxonomy/topics", response_model=list[TaxonomyTopicBriefOut])
def taxonomy_topics(
    subject: str | None = None,
    domain: str | None = None,
    grade: int | None = None,
    q: str | None = None,
    chapter: str | None = None,
    session: Session = Depends(get_session),
) -> list[TaxonomyTopicBriefOut]:
    query = session.query(Tag).filter(Tag.external_id.is_not(None))
    if subject:
        query = query.filter(Tag.subject == subject)
    if domain:
        query = query.filter(Tag.domain == domain)
    if grade is not None:
        query = query.filter(Tag.grade == grade)
    if chapter:
        query = query.filter(Tag.chapter == chapter)
    if q and q.strip():
        query = query.filter(Tag.name.like(f"%{q.strip()}%"))
    return [_brief(tag) for tag in _order(query.all())]


@router.get("/taxonomy/topics/{tag_id}", response_model=TaxonomyTopicDetailOut)
def taxonomy_topic(tag_id: str, session: Session = Depends(get_session)) -> TaxonomyTopicDetailOut:
    tag = session.get(Tag, tag_id)
    if tag is None or not tag.external_id:
        raise HTTPException(status_code=404, detail="知识点不存在")

    prerequisites = (
        session.query(TagEdge, Tag)
        .join(Tag, Tag.id == TagEdge.from_tag_id)
        .filter(TagEdge.to_tag_id == tag.id)
        .all()
    )
    dependents = (
        session.query(TagEdge, Tag)
        .join(Tag, Tag.id == TagEdge.to_tag_id)
        .filter(TagEdge.from_tag_id == tag.id)
        .all()
    )
    return TaxonomyTopicDetailOut(
        **_topic(tag).model_dump(),
        prerequisites=[_neighbor(other, edge) for edge, other in prerequisites],
        dependents=[_neighbor(other, edge) for edge, other in dependents],
        ancestors=[_brief(other) for other in _ancestors(session, {tag.id})],
    )


@router.get("/taxonomy/problems/{problem_id}/path", response_model=TaxonomyPathOut)
def taxonomy_problem_path(
    problem_id: str,
    depth: int = Query(default=MAX_DEPTH, ge=1, le=MAX_DEPTH),
    session: Session = Depends(get_session),
) -> TaxonomyPathOut:
    if session.get(Problem, problem_id) is None:
        raise HTTPException(status_code=404, detail="题目不存在")

    attached = (
        session.query(Tag)
        .join(ProblemTag, ProblemTag.tag_id == Tag.id)
        .filter(ProblemTag.problem_id == problem_id, Tag.external_id.is_not(None))
        .all()
    )
    attached = _order(attached)
    attached_ids = {tag.id for tag in attached}
    ancestors = _ancestors(session, attached_ids, depth)
    return TaxonomyPathOut(
        problem_id=problem_id,
        knowledge=[_brief(tag) for tag in attached],
        prerequisites=[_brief(tag) for tag in ancestors if tag.id not in attached_ids],
    )
