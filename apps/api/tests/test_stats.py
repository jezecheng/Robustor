"""WP6 · 统计口径与复习调度（SM-2 简化版）。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.db import SessionLocal
from app.models import Document, Problem, ProblemTag, Review, Tag, utcnow


def _overview(client) -> dict:
    response = client.get("/api/stats/overview")
    assert response.status_code == 200, response.text
    return response.json()


def _stat_map(items: list[dict]) -> dict[str, int]:
    return {item["name"]: item["count"] for item in items}


@pytest.fixture()
def data(client):
    """建 1 个文档 + 2 个不同学科的题 + approved 标签关联 + 1 条昨天到期的 review。"""
    baseline = _overview(client)

    with SessionLocal() as session:
        document = Document(subject="math", source_name="wp6-test", page_count=0)
        session.add(document)
        session.flush()

        math_problem = Problem(
            document_id=document.id,
            subject="math",
            stem_latex="x^2-5x+6=0",
            status="confirmed",
        )
        physics_problem = Problem(
            document_id=document.id,
            subject="physics",
            stem_latex="v=at",
            status="confirmed",
        )
        session.add_all([math_problem, physics_problem])
        session.flush()

        # 知识图谱可能与种子标签同名，按 (type, name) 取，避免覆盖。
        tags = {(tag.type, tag.name): tag.id for tag in session.query(Tag).all()}
        links = [
            (math_problem.id, tags[("knowledge", "一元二次方程")]),
            (math_problem.id, tags[("knowledge", "因式分解")]),
            (math_problem.id, tags[("method", "因式分解法")]),
            (physics_problem.id, tags[("knowledge", "勾股定理")]),
            (physics_problem.id, tags[("method", "数形结合")]),
        ]
        for problem_id, tag_id in links:
            session.add(ProblemTag(problem_id=problem_id, tag_id=tag_id, weight=1.0, source="ai"))

        session.add(
            Review(
                problem_id=math_problem.id,
                ease=2.5,
                interval_days=1,
                due_at=utcnow() - timedelta(days=1),
                history_json=[],
            )
        )
        session.commit()

        payload = {
            "document_id": document.id,
            "math_id": math_problem.id,
            "physics_id": physics_problem.id,
        }

    try:
        yield baseline, payload
    finally:
        with SessionLocal() as session:
            problem_ids = payload["math_id"], payload["physics_id"]
            session.query(Review).filter(Review.problem_id.in_(problem_ids)).delete(
                synchronize_session=False
            )
            session.query(ProblemTag).filter(ProblemTag.problem_id.in_(problem_ids)).delete(
                synchronize_session=False
            )
            session.query(Problem).filter(Problem.id.in_(problem_ids)).delete(
                synchronize_session=False
            )
            session.query(Document).filter(Document.id == payload["document_id"]).delete(
                synchronize_session=False
            )
            session.commit()


def test_overview_counts(client, data):
    baseline, _payload = data
    overview = _overview(client)

    assert overview["total"] == baseline["total"] + 2

    subjects = _stat_map(overview["by_subject"])
    assert subjects["math"] == _stat_map(baseline["by_subject"]).get("math", 0) + 1
    assert subjects["physics"] == _stat_map(baseline["by_subject"]).get("physics", 0) + 1

    knowledge = _stat_map(overview["by_knowledge"])
    baseline_knowledge = _stat_map(baseline["by_knowledge"])
    for name in ("一元二次方程", "因式分解", "勾股定理"):
        assert knowledge[name] == baseline_knowledge.get(name, 0) + 1

    methods = _stat_map(overview["by_method"])
    baseline_methods = _stat_map(baseline["by_method"])
    for name in ("因式分解法", "数形结合"):
        assert methods[name] == baseline_methods.get(name, 0) + 1

    # 昨天到期的 review 计入 due_today（due_at <= 今日 23:59:59）。
    assert overview["due_today"] == baseline["due_today"] + 1

    # 列表均按计数倒序。
    for key in ("by_subject", "by_knowledge", "by_method"):
        counts = [item["count"] for item in overview[key]]
        assert counts == sorted(counts, reverse=True)


def test_review_twice_extends_due_and_history(client, data):
    _baseline, payload = data
    problem_id = payload["math_id"]

    now = utcnow()
    first = client.post(f"/api/problems/{problem_id}/review", json={"grade": 3})
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["problem_id"] == problem_id
    assert first_body["ease"] == pytest.approx(2.5)
    # round(1 * 2.5 * 1.2) = 3
    assert first_body["interval_days"] == 3
    assert datetime.fromisoformat(first_body["due_at"]) > now

    second = client.post(f"/api/problems/{problem_id}/review", json={"grade": 3})
    assert second.status_code == 200, second.text
    second_body = second.json()
    # round(3 * 2.5 * 1.2) = 9
    assert second_body["interval_days"] == 9
    assert datetime.fromisoformat(second_body["due_at"]) > datetime.fromisoformat(
        first_body["due_at"]
    )

    with SessionLocal() as session:
        review = session.query(Review).filter(Review.problem_id == problem_id).one()
        assert review.interval_days == 9
        assert len(review.history_json) == 2
        assert [entry["grade"] for entry in review.history_json] == [3, 3]
        assert review.history_json[-1]["interval_days"] == 9
        assert "at" in review.history_json[-1]


def test_review_forgot_resets_interval_and_lowers_ease(client, data):
    _baseline, payload = data
    problem_id = payload["physics_id"]

    response = client.post(f"/api/problems/{problem_id}/review", json={"grade": 0})
    assert response.status_code == 200, response.text
    body = response.json()
    # review 不存在时按默认 ease=2.5 创建，grade<2 减去 0.2 并重置为 1 天。
    assert body["ease"] == pytest.approx(2.3)
    assert body["interval_days"] == 1
    due_at = datetime.fromisoformat(body["due_at"])
    assert utcnow() < due_at <= utcnow() + timedelta(days=2)

    with SessionLocal() as session:
        review = session.query(Review).filter(Review.problem_id == problem_id).one()
        assert len(review.history_json) == 1
        assert review.history_json[0]["grade"] == 0


def test_review_unknown_problem_returns_404(client):
    response = client.post("/api/problems/not-exist/review", json={"grade": 3})
    assert response.status_code == 404
    assert response.json()["detail"] == "题目不存在"
