"""WP4 · 标签词表。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import ProblemTag, Tag
from ..schemas import TagIn, TagMergeIn, TagOut
from ..textutil import normalize_name

router = APIRouter(tags=["tags"])


def _tag_out(tag: Tag) -> TagOut:
    return TagOut.model_validate(tag)


@router.get("/tags", response_model=list[TagOut])
def list_tags(
    type: str | None = None,
    q: str | None = None,
    status: str | None = None,
    session: Session = Depends(get_session),
) -> list[TagOut]:
    query = session.query(Tag)
    if type:
        query = query.filter(Tag.type == type)
    if status:
        query = query.filter(Tag.status == status)
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(Tag.name.like(like), Tag.normalized_name.like(like)))
    return [_tag_out(tag) for tag in query.order_by(Tag.type, Tag.name).all()]


@router.post("/tags", response_model=TagOut, status_code=201)
def create_tag(payload: TagIn, session: Session = Depends(get_session)) -> TagOut:
    name = (payload.name or "").strip()
    normalized = normalize_name(name)
    if not normalized:
        raise HTTPException(status_code=400, detail="标签名不能为空")
    if payload.parent_id and session.get(Tag, payload.parent_id) is None:
        raise HTTPException(status_code=400, detail="父标签不存在")
    exists = (
        session.query(Tag)
        .filter(Tag.type == payload.type, Tag.normalized_name == normalized)
        .first()
    )
    if exists is not None:
        raise HTTPException(status_code=409, detail="标签已存在")

    tag = Tag(
        type=payload.type,
        name=name,
        normalized_name=normalized,
        parent_id=payload.parent_id,
        status="pending",
    )
    session.add(tag)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="标签已存在")
    session.refresh(tag)
    return _tag_out(tag)


@router.post("/tags/merge", response_model=TagOut)
def merge_tags(payload: TagMergeIn, session: Session = Depends(get_session)) -> TagOut:
    if payload.from_id == payload.to_id:
        raise HTTPException(status_code=400, detail="不能合并到自身")
    source = session.get(Tag, payload.from_id)
    target = session.get(Tag, payload.to_id)
    if source is None or target is None:
        raise HTTPException(status_code=404, detail="标签不存在")

    existing = {
        row[0]
        for row in session.query(ProblemTag.problem_id)
        .filter(ProblemTag.tag_id == target.id)
        .all()
    }
    for link in session.query(ProblemTag).filter(ProblemTag.tag_id == source.id).all():
        if link.problem_id in existing:
            session.delete(link)
        else:
            link.tag_id = target.id
            existing.add(link.problem_id)

    session.query(Tag).filter(Tag.parent_id == source.id).update(
        {Tag.parent_id: target.id}, synchronize_session=False
    )
    session.delete(source)
    session.commit()
    session.refresh(target)
    return _tag_out(target)


@router.get("/tags/pending", response_model=list[TagOut])
def pending_tags(session: Session = Depends(get_session)) -> list[TagOut]:
    rows = (
        session.query(Tag)
        .filter(Tag.status == "pending")
        .order_by(Tag.type, Tag.name)
        .all()
    )
    return [_tag_out(tag) for tag in rows]
