"""WP1 · 题目 CRUD（含 solutions / tags 关联读写）。"""

from __future__ import annotations

from datetime import datetime, time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import (
    Document,
    Mark,
    Problem,
    ProblemImage,
    ProblemTag,
    Region,
    Review,
    Solution,
    Tag,
    utcnow,
)
from ..schemas import (
    MarkIn,
    MarkOut,
    ProblemCreate,
    ProblemImageOut,
    ProblemListOut,
    ProblemOut,
    ProblemPatch,
    ProblemTagOut,
    ProblemTagsIn,
    SolutionIn,
    SolutionOut,
)

router = APIRouter(tags=["problems"])


def _get_problem(session: Session, problem_id: str) -> Problem:
    problem = session.get(Problem, problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="题目不存在")
    return problem


def _problem_out(session: Session, problem: Problem) -> ProblemOut:
    images = (
        session.query(ProblemImage)
        .filter(ProblemImage.problem_id == problem.id)
        .all()
    )
    solutions = (
        session.query(Solution).filter(Solution.problem_id == problem.id).all()
    )
    marks = session.query(Mark).filter(Mark.problem_id == problem.id).all()
    tag_rows = (
        session.query(ProblemTag, Tag)
        .join(Tag, Tag.id == ProblemTag.tag_id)
        .filter(ProblemTag.problem_id == problem.id)
        .order_by(Tag.type, Tag.name)
        .all()
    )
    return ProblemOut(
        id=problem.id,
        document_id=problem.document_id,
        subject=problem.subject,
        stem_latex=problem.stem_latex,
        stem_text=problem.stem_text,
        status=problem.status,
        created_at=problem.created_at,
        images=[ProblemImageOut.model_validate(image) for image in images],
        solutions=[
            SolutionOut(
                id=item.id,
                problem_id=item.problem_id,
                kind=item.kind,
                latex=item.latex,
                ink_role=item.ink_role,
                confidence=item.confidence,
            )
            for item in solutions
        ],
        marks=[
            MarkOut(
                id=item.id,
                problem_id=item.problem_id,
                region_id=item.region_id,
                verdict=item.verdict,
                raw_symbol=item.raw_symbol,
                score=item.score,
                solution_id=item.solution_id,
            )
            for item in marks
        ],
        tags=[
            ProblemTagOut(
                id=tag.id, type=tag.type, name=tag.name, source=link.source, weight=link.weight
            )
            for link, tag in tag_rows
        ],
    )


def _load_regions(session: Session, document_id: str, region_ids: list[str]) -> list[Region]:
    ids = list(dict.fromkeys(region_ids))
    if not ids:
        return []
    regions = session.query(Region).filter(Region.id.in_(ids)).all()
    if len(regions) != len(ids):
        raise HTTPException(status_code=404, detail="存在无效的 region_id")
    for region in regions:
        if region.document_id != document_id:
            raise HTTPException(status_code=400, detail="region 不属于该文档")
    return regions


def _replace_solutions(session: Session, problem_id: str, items: list[SolutionIn]) -> None:
    session.query(Solution).filter(Solution.problem_id == problem_id).delete(
        synchronize_session=False
    )
    for item in items:
        session.add(
            Solution(
                problem_id=problem_id,
                kind=item.kind,
                latex=item.latex,
                ink_role=item.ink_role,
                confidence=item.confidence,
            )
        )


def _replace_marks(session: Session, problem_id: str, items: list[MarkIn]) -> None:
    session.query(Mark).filter(Mark.problem_id == problem_id).delete(synchronize_session=False)
    for item in items:
        session.add(
            Mark(
                problem_id=problem_id,
                region_id=None,
                verdict=item.verdict,
                raw_symbol=item.raw_symbol,
                score=item.score,
                solution_id=item.solution_id,
            )
        )


@router.post("/problems", response_model=ProblemOut, status_code=201)
def create_problem(payload: ProblemCreate, session: Session = Depends(get_session)) -> ProblemOut:
    """人工确认入库：region_ids 全部指向同一 draft problem 时更新它，否则新建 confirmed。"""
    if session.get(Document, payload.document_id) is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    regions = _load_regions(session, payload.document_id, payload.region_ids)

    target: Problem | None = None
    if regions:
        bound = {region.problem_id for region in regions}
        if len(bound) == 1 and None not in bound:
            candidate = session.get(Problem, next(iter(bound)))
            if candidate is not None and candidate.status == "draft":
                target = candidate

    if target is not None:
        if payload.stem_latex.strip():
            target.stem_latex = payload.stem_latex
        target.subject = payload.subject
        target.status = "confirmed"
        problem = target
    else:
        problem = Problem(
            document_id=payload.document_id,
            subject=payload.subject,
            stem_latex=payload.stem_latex,
            stem_text="",
            status="confirmed",
        )
        session.add(problem)
        session.flush()
        for region in regions:
            region.problem_id = problem.id

    if payload.solutions:
        _replace_solutions(session, problem.id, payload.solutions)
    if payload.marks:
        _replace_marks(session, problem.id, payload.marks)

    session.commit()
    session.refresh(problem)
    return _problem_out(session, problem)


@router.get("/problems", response_model=ProblemListOut)
def list_problems(
    subject: str | None = None,
    tag_id: list[str] | None = Query(default=None),
    verdict: str | None = None,
    due: Literal["today", "overdue"] | None = None,
    q: str | None = None,
    status: Literal["draft", "confirmed", "all"] = "confirmed",
    page: int = 1,
    size: int = 20,
    session: Session = Depends(get_session),
) -> ProblemListOut:
    query = session.query(Problem)
    if status != "all":
        query = query.filter(Problem.status == status)
    if subject:
        query = query.filter(Problem.subject == subject)
    for tag in tag_id or []:
        query = query.filter(
            Problem.id.in_(
                session.query(ProblemTag.problem_id).filter(ProblemTag.tag_id == tag)
            )
        )
    if verdict:
        query = query.filter(
            Problem.id.in_(
                session.query(Mark.problem_id).filter(
                    Mark.verdict == verdict, Mark.problem_id.isnot(None)
                )
            )
        )
    if due == "overdue":
        query = query.filter(
            Problem.id.in_(
                session.query(Review.problem_id).filter(Review.due_at < utcnow())
            )
        )
    elif due == "today":
        end_of_day = datetime.combine(utcnow().date(), time(23, 59, 59))
        query = query.filter(
            Problem.id.in_(
                session.query(Review.problem_id).filter(Review.due_at <= end_of_day)
            )
        )
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(Problem.stem_latex.ilike(like), Problem.stem_text.ilike(like))
        )

    total = query.count()
    page = max(1, page)
    size = max(1, min(size, 100))
    rows = (
        query.order_by(Problem.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return ProblemListOut(
        items=[_problem_out(session, problem) for problem in rows],
        total=total,
        page=page,
        size=size,
    )


@router.get("/problems/{problem_id}", response_model=ProblemOut)
def get_problem(problem_id: str, session: Session = Depends(get_session)) -> ProblemOut:
    return _problem_out(session, _get_problem(session, problem_id))


@router.patch("/problems/{problem_id}", response_model=ProblemOut)
def patch_problem(
    problem_id: str, payload: ProblemPatch, session: Session = Depends(get_session)
) -> ProblemOut:
    problem = _get_problem(session, problem_id)
    if payload.stem_latex is not None:
        problem.stem_latex = payload.stem_latex
    if payload.subject is not None:
        problem.subject = payload.subject
    if payload.status is not None:
        problem.status = payload.status
    session.commit()
    session.refresh(problem)
    return _problem_out(session, problem)


@router.delete("/problems/{problem_id}", status_code=204)
def delete_problem(problem_id: str, session: Session = Depends(get_session)) -> None:
    problem = _get_problem(session, problem_id)
    session.query(Mark).filter(Mark.problem_id == problem.id).delete(synchronize_session=False)
    session.query(ProblemTag).filter(ProblemTag.problem_id == problem.id).delete(
        synchronize_session=False
    )
    session.query(Review).filter(Review.problem_id == problem.id).delete(synchronize_session=False)
    session.query(Solution).filter(Solution.problem_id == problem.id).delete(
        synchronize_session=False
    )
    session.query(ProblemImage).filter(ProblemImage.problem_id == problem.id).delete(
        synchronize_session=False
    )
    session.query(Region).filter(Region.problem_id == problem.id).update(
        {Region.problem_id: None}, synchronize_session=False
    )
    session.delete(problem)
    session.commit()


@router.put("/problems/{problem_id}/solutions", response_model=list[SolutionOut])
def replace_solutions(
    problem_id: str, payload: list[SolutionIn], session: Session = Depends(get_session)
) -> list[SolutionOut]:
    problem = _get_problem(session, problem_id)
    _replace_solutions(session, problem.id, payload)
    session.commit()
    rows = session.query(Solution).filter(Solution.problem_id == problem.id).all()
    return [
        SolutionOut(
            id=item.id,
            problem_id=item.problem_id,
            kind=item.kind,
            latex=item.latex,
            ink_role=item.ink_role,
            confidence=item.confidence,
        )
        for item in rows
    ]


@router.put("/problems/{problem_id}/tags", response_model=list[ProblemTagOut])
def replace_tags(
    problem_id: str, payload: ProblemTagsIn, session: Session = Depends(get_session)
) -> list[ProblemTagOut]:
    problem = _get_problem(session, problem_id)

    def resolve(tag_ids: list[str], expected: str) -> list[Tag]:
        resolved: list[Tag] = []
        for tag_id in dict.fromkeys(tag_ids):
            tag = session.get(Tag, tag_id)
            if tag is None:
                raise HTTPException(status_code=400, detail=f"标签不存在: {tag_id}")
            if tag.type != expected:
                raise HTTPException(status_code=400, detail=f"标签类型不匹配: {tag.name}")
            resolved.append(tag)
        return resolved

    knowledge = resolve(payload.knowledge, "knowledge")
    method = resolve(payload.method, "method")

    session.query(ProblemTag).filter(ProblemTag.problem_id == problem.id).delete(
        synchronize_session=False
    )
    for tag in knowledge + method:
        session.add(
            ProblemTag(problem_id=problem.id, tag_id=tag.id, weight=1.0, source="manual")
        )
    session.commit()
    return [
        ProblemTagOut(id=tag.id, type=tag.type, name=tag.name, source="manual", weight=1.0)
        for tag in knowledge + method
    ]
