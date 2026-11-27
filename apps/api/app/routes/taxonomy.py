"""知识图谱：按学科浏览、节点详情、先修链、题目诊断路径。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Problem, ProblemTag, Tag, TagEdge
from ..schemas import (
    TaxonomyClusterOut,
    TaxonomyFacetOut,
    TaxonomyGraphEdgeOut,
    TaxonomyGraphOut,
    TaxonomyNeighborOut,
    TaxonomyPathOut,
    TaxonomySummaryOut,
    TaxonomyTopicBriefOut,
    TaxonomyTopicDetailOut,
    TaxonomyTopicOut,
)
from ..clusters import (
    cluster_name_of,
    cluster_parent_of,
    clusters_of,
    member_ids,
    parent_member_ids,
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
        cluster=cluster_name_of(tag.external_id),
        cluster_parent=cluster_parent_of(tag.external_id),
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


@router.get("/taxonomy/clusters", response_model=list[TaxonomyClusterOut])
def taxonomy_clusters(
    subject: str | None = None,
    parent: str | None = None,
    session: Session = Depends(get_session),
) -> list[TaxonomyClusterOut]:
    """主题分组列表（含分组内知识点数量）。parent 用于取某个领域的二级分组。"""
    result: list[TaxonomyClusterOut] = []
    for cluster in clusters_of(subject, parent):
        count = (
            session.query(Tag)
            .filter(Tag.external_id.in_(cluster["members"]))
            .count()
        )
        result.append(
            TaxonomyClusterOut(
                id=cluster["id"],
                subject=cluster["subject"],
                parent=cluster["parent"],
                name=cluster["name"],
                count=count,
            )
        )
    return result


@router.get("/taxonomy/topics", response_model=list[TaxonomyTopicBriefOut])
def taxonomy_topics(
    subject: str | None = None,
    domain: str | None = None,
    grade: int | None = None,
    q: str | None = None,
    chapter: str | None = None,
    cluster: str | None = None,
    parent: str | None = None,
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
    if parent:
        members = parent_member_ids(subject, parent)
        if not members:
            return []
        query = query.filter(Tag.external_id.in_(members))
    if cluster:
        members = member_ids(cluster)
        if not members:
            return []
        query = query.filter(Tag.external_id.in_(members))
    if q and q.strip():
        query = query.filter(Tag.name.like(f"%{q.strip()}%"))
    return [_brief(tag) for tag in _order(query.all())]


def _expand(session: Session, focus: Tag, depth: int) -> list[Tag]:
    """从 focus 出发双向扩展 depth 跳，只保留图谱内（有 external_id）的知识点。"""
    found: dict[str, Tag] = {focus.id: focus}
    frontier = {focus.id}
    for _ in range(depth):
        if not frontier:
            break
        rows = (
            session.query(TagEdge)
            .filter(or_(TagEdge.from_tag_id.in_(frontier), TagEdge.to_tag_id.in_(frontier)))
            .all()
        )
        next_frontier: set[str] = set()
        for edge in rows:
            for tag_id in (edge.from_tag_id, edge.to_tag_id):
                if tag_id in found:
                    continue
                next_frontier.add(tag_id)
        if not next_frontier:
            break
        for tag in session.query(Tag).filter(Tag.id.in_(next_frontier)):
            if tag.external_id:
                found[tag.id] = tag
        frontier = next_frontier
    return _order(list(found.values()))


@router.get("/taxonomy/graph", response_model=TaxonomyGraphOut)
def taxonomy_graph(
    subject: str | None = None,
    domain: str | None = None,
    grade: int | None = None,
    chapter: str | None = None,
    q: str | None = None,
    cluster: str | None = None,
    parent: str | None = None,
    focus: str | None = None,
    depth: int = Query(default=1, ge=1, le=3),
    limit: int = Query(default=160, ge=20, le=400),
    session: Session = Depends(get_session),
) -> TaxonomyGraphOut:
    """图谱视图数据：一批知识点节点及其之间的先修边。

    - 默认按筛选条件取节点（受 limit 截断，total 为截断前数量）；
    - 传 focus 时改为聚焦模式，返回该知识点 depth 跳内的先修邻域。
    """
    if focus:
        center = session.get(Tag, focus)
        if center is None or not center.external_id:
            raise HTTPException(status_code=404, detail="知识点不存在")
        tags = _expand(session, center, depth)
        total = len(tags)
        truncated = False
    else:
        query = session.query(Tag).filter(Tag.external_id.is_not(None))
        if subject:
            query = query.filter(Tag.subject == subject)
        if domain:
            query = query.filter(Tag.domain == domain)
        if grade is not None:
            query = query.filter(Tag.grade == grade)
        if chapter:
            query = query.filter(Tag.chapter == chapter)
        if parent:
            members = parent_member_ids(subject, parent)
            if not members:
                return TaxonomyGraphOut(nodes=[], edges=[], total=0, truncated=False)
            query = query.filter(Tag.external_id.in_(members))
        if cluster:
            members = member_ids(cluster)
            if not members:
                return TaxonomyGraphOut(nodes=[], edges=[], total=0, truncated=False)
            query = query.filter(Tag.external_id.in_(members))
        if q and q.strip():
            query = query.filter(Tag.name.like(f"%{q.strip()}%"))
        total = query.count()
        tags = _order(query.all())[:limit]
        truncated = total > len(tags)

    ids = [tag.id for tag in tags]
    edges: list[TaxonomyGraphEdgeOut] = []
    if ids:
        rows = (
            session.query(TagEdge)
            .filter(TagEdge.from_tag_id.in_(ids), TagEdge.to_tag_id.in_(ids))
            .all()
        )
        edges = [
            TaxonomyGraphEdgeOut(
                source=edge.from_tag_id,
                target=edge.to_tag_id,
                strength=edge.strength,
                reason=edge.reason or "",
            )
            for edge in rows
        ]
    return TaxonomyGraphOut(
        nodes=[_brief(tag) for tag in tags],
        edges=edges,
        total=total,
        truncated=truncated,
    )


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
