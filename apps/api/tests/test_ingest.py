"""WP1 冒烟：上传 3 页 fixture → 流水线跑完 → 区域可改 → 确认入库可查。"""

from __future__ import annotations

from app.config import FIXTURE_DEMO_DIR


def _upload_demo(client):
    files = [
        ("files", (name, (FIXTURE_DEMO_DIR / name).read_bytes(), "image/jpeg"))
        for name in ("p1.jpg", "p2.jpg", "p3.jpg")
    ]
    return client.post("/api/documents", files=files, data={"subject": "math"})


def test_upload_empty_files_returns_400(client):
    response = client.post("/api/documents", files=[], data={"subject": "math"})
    assert response.status_code == 400, response.text


def test_upload_pipeline_regions_and_confirm(client):
    document_id = None
    problem_id = None
    try:
        response = _upload_demo(client)
        assert response.status_code == 201, response.text
        created = response.json()
        document_id = created["document_id"]
        job_id = created["job_id"]

        # TestClient 会同步跑完 BackgroundTasks，返回时 job 应为 done
        job = client.get(f"/api/jobs/{job_id}")
        assert job.status_code == 200
        assert job.json()["status"] == "done", job.json()
        assert job.json()["progress"] == 1.0

        detail = client.get(f"/api/documents/{document_id}")
        assert detail.status_code == 200
        document = detail.json()
        assert document["page_count"] == 3
        assert [page["idx"] for page in document["pages"]] == [1, 2, 3]
        assert all(page["region_count"] > 0 for page in document["pages"])
        assert document["job"]["id"] == job_id

        regions = client.get(f"/api/documents/{document_id}/regions")
        assert regions.status_code == 200
        region_list = regions.json()
        assert len(region_list) >= 5
        assert len({region["block_type"] for region in region_list}) >= 5

        # PATCH：bbox 越界值逐值 clamp 到 [0, 1]
        patched = client.patch(
            f"/api/regions/{region_list[0]['id']}",
            json={"bbox": [1.4, -0.2, 0.5, 0.1]},
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["bbox"] == [1.0, 0.0, 0.5, 0.1]

        # page_end < page_start 应拒绝
        invalid = client.patch(
            f"/api/regions/{region_list[0]['id']}",
            json={"page_start": 3, "page_end": 1},
        )
        assert invalid.status_code == 400

        # 找到 s5 装配出来的 draft problem，并取它绑定的 region_ids
        from app.db import SessionLocal
        from app.models import Problem, Region

        with SessionLocal() as session:
            draft = (
                session.query(Problem)
                .filter(Problem.document_id == document_id, Problem.status == "draft")
                .first()
            )
            assert draft is not None, "s5 应产出 draft problem"
            draft_id = draft.id
            region_ids = [
                row.id
                for row in session.query(Region).filter(Region.problem_id == draft.id).all()
            ]
        assert region_ids

        # region_ids 全部指向同一 draft → 更新该题并置 confirmed，而不是新建
        confirmed = client.post(
            "/api/problems",
            json={
                "document_id": document_id,
                "region_ids": region_ids,
                "stem_latex": "x^2-5x+6=0",
                "subject": "math",
            },
        )
        assert confirmed.status_code == 201, confirmed.text
        problem = confirmed.json()
        problem_id = problem["id"]
        assert problem["id"] == draft_id
        assert problem["status"] == "confirmed"
        assert problem["stem_latex"] == "x^2-5x+6=0"
        assert problem["solutions"], "s5 装配的解答应被保留"
        assert problem["marks"], "s4 识别出的批改标记应保留"

        listed = client.get("/api/problems", params={"subject": "math", "q": "x^2-5x+6"})
        assert listed.status_code == 200
        envelope = listed.json()
        assert set(envelope) == {"items", "total", "page", "size"}
        assert envelope["total"] >= 1
        assert any(item["id"] == problem["id"] for item in envelope["items"])

        fetched = client.get(f"/api/problems/{problem['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["status"] == "confirmed"
        assert client.get("/api/problems/not-exist").status_code == 404
    finally:
        if document_id:
            deleted = client.delete(f"/api/documents/{document_id}")
            assert deleted.status_code == 204
            assert client.get(f"/api/documents/{document_id}").status_code == 404
            if problem_id:
                # 默认 delete_problems=true：题目随作业一起删除
                assert client.get(f"/api/problems/{problem_id}").status_code == 404


def test_delete_document_can_keep_confirmed_problems(client):
    """删除作业时选择保留错题：题目与批改结果留在错题本，图片与区域被清理。"""
    document_id = None
    problem_id = None
    try:
        response = _upload_demo(client)
        assert response.status_code == 201, response.text
        document_id = response.json()["document_id"]

        from app.db import SessionLocal
        from app.models import Problem, Region

        with SessionLocal() as session:
            draft = (
                session.query(Problem)
                .filter(Problem.document_id == document_id, Problem.status == "draft")
                .first()
            )
            assert draft is not None, "s5 应产出 draft problem"
            region_ids = [
                row.id
                for row in session.query(Region).filter(Region.problem_id == draft.id).all()
            ]
        assert region_ids

        confirmed = client.post(
            "/api/problems",
            json={
                "document_id": document_id,
                "region_ids": region_ids,
                "stem_latex": "x+1=2",
                "subject": "math",
            },
        )
        assert confirmed.status_code == 201, confirmed.text
        problem_id = confirmed.json()["id"]

        deleted = client.delete(
            f"/api/documents/{document_id}", params={"delete_problems": "false"}
        )
        assert deleted.status_code == 204
        assert client.get(f"/api/documents/{document_id}").status_code == 404
        assert client.get(f"/api/documents/{document_id}/regions").status_code == 404

        kept = client.get(f"/api/problems/{problem_id}")
        assert kept.status_code == 200, kept.text
        problem = kept.json()
        assert problem["status"] == "confirmed"
        assert problem["marks"], "保留错题时批改标记应保留"
        assert problem["solutions"], "保留错题时解答应保留"
        assert all(mark["region_id"] is None for mark in problem["marks"])
        assert all(image["region_id"] is None for image in problem["images"])

        with SessionLocal() as session:
            assert session.query(Region).filter(Region.document_id == document_id).count() == 0
    finally:
        if problem_id:
            client.delete(f"/api/problems/{problem_id}")
        if document_id:
            client.delete(f"/api/documents/{document_id}")
