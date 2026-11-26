def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_documents_list_empty(client):
    response = client.get("/api/documents")
    assert response.status_code == 200
    assert response.json() == []


def test_openapi_available(client):
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    for path in ("/api/documents", "/api/regions/{region_id}", "/api/problems", "/api/stats/overview"):
        assert path in paths


def test_seeded_tags(client):
    from app.db import SessionLocal
    from app.models import InkProfile, Tag
    from app.taxonomy import load_topics

    with SessionLocal() as session:
        # 60 个种子标签 + 内置知识图谱（同步后 external_id 非空）
        assert session.query(Tag).filter(Tag.external_id.is_(None)).count() >= 55
        assert session.query(Tag).filter(Tag.external_id.is_not(None)).count() == len(load_topics())
        assert session.query(Tag).filter(Tag.name == "一元二次方程").count() >= 1
        assert session.query(InkProfile).filter(InkProfile.is_default.is_(True)).count() == 1
