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

    with SessionLocal() as session:
        assert session.query(Tag).count() == 60
        assert session.query(InkProfile).filter(InkProfile.is_default.is_(True)).count() == 1
