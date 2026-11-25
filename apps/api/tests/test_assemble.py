"""WP4 · 三页 fixture 在 mock 模式下跑 layout→ink→recognize→assemble→tag。"""

from __future__ import annotations

import pytest

from app.config import FIXTURE_DEMO_DIR, ensure_dirs
from app.db import SessionLocal, init_db
from app.models import (
    Document,
    Mark,
    Page,
    Problem,
    ProblemImage,
    ProblemTag,
    Region,
    Review,
    Solution,
    Tag,
)
from app.pipeline import s1_preprocess, s2_layout, s3_ink, s4_recognize, s5_assemble, s6_tag
from app.pipeline.base import StageContext
from app.seeds import seed_all
from app.storage import Storage

PAGE_STAGES = (s1_preprocess.STAGE, s2_layout.STAGE, s3_ink.STAGE, s4_recognize.STAGE)


@pytest.fixture()
def env():
    ensure_dirs()
    init_db()
    session = SessionLocal()
    seed_all(session)
    tag_ids_before = {row[0] for row in session.query(Tag.id).all()}
    storage = Storage()
    document_id = _create_document(session, storage)
    try:
        yield session, storage, document_id
    finally:
        _cleanup(session, document_id, tag_ids_before)
        session.close()


def _create_document(session, storage) -> str:
    document = Document(subject="math", source_name="fixture-3p", page_count=3)
    session.add(document)
    session.flush()
    for idx in (1, 2, 3):
        data = (FIXTURE_DEMO_DIR / f"p{idx}.jpg").read_bytes()
        rel, width, height = storage.save_page(document.id, idx, data)
        session.add(
            Page(
                document_id=document.id,
                idx=idx,
                image_path=rel,
                width=width,
                height=height,
                status="pending",
            )
        )
    session.commit()
    return document.id


def _run_pipeline(session, storage, document_id):
    pages = (
        session.query(Page).filter(Page.document_id == document_id).order_by(Page.idx).all()
    )
    for stage in PAGE_STAGES:
        for page in pages:
            result = stage.run(StageContext(document_id, page.id, session, storage, {}))
            assert result.ok, (stage.name, result.warnings)
    assemble = s5_assemble.STAGE.run(StageContext(document_id, None, session, storage, {}))
    tag = s6_tag.STAGE.run(StageContext(document_id, None, session, storage, {}))
    assert assemble.ok and tag.ok
    return assemble, tag


def _problems(session, document_id) -> dict[str, Problem]:
    problems = session.query(Problem).filter(Problem.document_id == document_id).all()
    result: dict[str, Problem] = {}
    for problem in problems:
        if "x^2 - 5x + 6" in problem.stem_text:
            result["quad1"] = problem
        elif "2x^2 + 3x - 2" in problem.stem_text:
            result["quad2"] = problem
        elif "triangle" in problem.stem_text:
            result["triangle"] = problem
    return result


def _tag_names(session, problem_id, tag_type) -> set[str]:
    rows = (
        session.query(Tag)
        .join(ProblemTag, ProblemTag.tag_id == Tag.id)
        .filter(
            ProblemTag.problem_id == problem_id,
            Tag.type == tag_type,
            Tag.status == "approved",
        )
        .all()
    )
    return {row.name for row in rows}


def test_assemble_three_problems_with_cross_page_merge(env):
    session, storage, document_id = env
    assemble, tag = _run_pipeline(session, storage, document_id)

    assert assemble.stats["problems"] == 3
    assert assemble.stats["merged_cross_page"] == 1
    assert assemble.stats["figures_bound"] == 2
    assert tag.stats["problems"] == 3

    problems = _problems(session, document_id)
    assert set(problems) == {"quad1", "quad2", "triangle"}

    # 第 2 页截断的题干与第 3 页续写合并成一道题
    assert problems["triangle"].stem_text == (
        "3. In triangle ABC, AB = 5, AC = 12,\nangle A = 90 deg. Find BC and the area."
    )
    cross_page = []
    for key, problem in problems.items():
        rows = (
            session.query(Region, Page.idx)
            .join(Page, Page.id == Region.page_id)
            .filter(Region.problem_id == problem.id)
            .all()
        )
        page_idxs = {idx for _region, idx in rows}
        if len(page_idxs) > 1 or any(region.page_start != region.page_end for region, _ in rows):
            cross_page.append(key)
    assert cross_page == ["triangle"]

    # 第 1、3 题各绑定一张附图；第 2 题无图
    for key in ("quad1", "triangle"):
        images = (
            session.query(ProblemImage)
            .filter(ProblemImage.problem_id == problems[key].id)
            .all()
        )
        assert len(images) == 1
        assert images[0].caption == "图 1"
    assert (
        session.query(ProblemImage)
        .filter(ProblemImage.problem_id == problems["quad2"].id)
        .count()
        == 0
    )

    # 每题至少 1 个 approved knowledge 标签，且没有任何 pending 标签被绑定
    for problem in problems.values():
        assert _tag_names(session, problem.id, "knowledge")
        pending_bound = (
            session.query(ProblemTag)
            .join(Tag, Tag.id == ProblemTag.tag_id)
            .filter(ProblemTag.problem_id == problem.id, Tag.status != "approved")
            .count()
        )
        assert pending_bound == 0

    knowledge = {name for problem in problems.values() for name in _tag_names(session, problem.id, "knowledge")}
    method = {name for problem in problems.values() for name in _tag_names(session, problem.id, "method")}
    assert {"一元二次方程", "勾股定理", "三角形面积"} <= knowledge
    assert {"因式分解法", "公式法", "数形结合"} <= method

    # answer → student solution，correction → correction solution，mark 回填到题
    solutions = (
        session.query(Solution).filter(Solution.problem_id == problems["quad1"].id).all()
    )
    assert {solution.kind for solution in solutions} == {"student", "correction"}
    assert session.query(Mark).filter(Mark.problem_id == problems["quad1"].id).count() == 1


def _counts(session, document_id) -> dict[str, int]:
    problem_ids = session.query(Problem.id).filter(Problem.document_id == document_id)
    return {
        "problems": problem_ids.count(),
        "solutions": session.query(Solution)
        .filter(Solution.problem_id.in_(problem_ids))
        .count(),
        "images": session.query(ProblemImage)
        .filter(ProblemImage.problem_id.in_(problem_ids))
        .count(),
        "tags": session.query(ProblemTag)
        .filter(ProblemTag.problem_id.in_(problem_ids))
        .count(),
    }


def test_assemble_and_tag_are_idempotent(env):
    session, storage, document_id = env
    _run_pipeline(session, storage, document_id)
    first = _counts(session, document_id)

    assemble, tag = _run_pipeline(session, storage, document_id)
    assert assemble.stats["problems"] == 3
    assert session.query(Problem).filter(Problem.document_id == document_id).count() == 3
    assert _counts(session, document_id) == first



def _cleanup(session, document_id, tag_ids_before) -> None:
    session.rollback()
    problem_ids = [
        row[0]
        for row in session.query(Problem.id).filter(Problem.document_id == document_id).all()
    ]
    if problem_ids:
        session.query(ProblemImage).filter(ProblemImage.problem_id.in_(problem_ids)).delete(
            synchronize_session=False
        )
        session.query(ProblemTag).filter(ProblemTag.problem_id.in_(problem_ids)).delete(
            synchronize_session=False
        )
        session.query(Solution).filter(Solution.problem_id.in_(problem_ids)).delete(
            synchronize_session=False
        )
        session.query(Mark).filter(Mark.problem_id.in_(problem_ids)).delete(
            synchronize_session=False
        )
        session.query(Review).filter(Review.problem_id.in_(problem_ids)).delete(
            synchronize_session=False
        )
        session.query(Problem).filter(Problem.id.in_(problem_ids)).delete(synchronize_session=False)
    session.query(Region).filter(Region.document_id == document_id).delete(
        synchronize_session=False
    )
    session.query(Page).filter(Page.document_id == document_id).delete(synchronize_session=False)
    session.query(Document).filter(Document.id == document_id).delete(synchronize_session=False)
    for tag in session.query(Tag).all():
        if tag.id not in tag_ids_before:
            session.query(ProblemTag).filter(ProblemTag.tag_id == tag.id).delete(
                synchronize_session=False
            )
            session.delete(tag)
    session.commit()
