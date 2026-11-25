"""WP7 冒烟：墨迹方案列表 / 新建 / 修改 / 校验。

用例自建的方案在结束后删除并恢复唯一默认，避免影响 test_smoke 的“默认方案只有 1 条”断言。
"""

from __future__ import annotations

import pytest

VALID_RULES = {
    "name": "测试方案",
    "roles": [
        {"role": "print", "color": "black", "mode": "printed", "sat_max": 40},
        {"role": "answer", "color": "black", "mode": "handwritten", "sat_max": 40},
        {"role": "mark", "color": "red", "hue": [-15, 20], "sat_min": 80},
        {"role": "correction", "color": "blue", "hue": [200, 255], "sat_min": 70},
    ],
    "page_overrides": {"3": {"roles": []}},
}


@pytest.fixture()
def created_profile_ids(client):
    """收集本用例新建的方案 id，结束后清理并恢复唯一默认。"""
    ids: list[str] = []
    yield ids

    from app.db import SessionLocal
    from app.models import InkProfile

    with SessionLocal() as session:
        for profile_id in ids:
            profile = session.get(InkProfile, profile_id)
            if profile is not None:
                session.delete(profile)
        session.commit()
        if session.query(InkProfile).filter(InkProfile.is_default.is_(True)).count() == 0:
            fallback = session.query(InkProfile).first()
            if fallback is not None:
                fallback.is_default = True
                session.commit()


def _create(client, name: str = "临时方案") -> dict:
    response = client.post(
        "/api/ink-profiles",
        json={"name": name, "is_default": False, "rules_json": VALID_RULES},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_list_ink_profiles_unique_default_first(client):
    response = client.get("/api/ink-profiles")
    assert response.status_code == 200
    items = response.json()

    assert len(items) >= 1
    defaults = [item for item in items if item["is_default"]]
    assert len(defaults) == 1
    assert items[0]["is_default"] is True
    assert isinstance(items[0]["rules_json"].get("roles"), list)


def test_create_profile_increments_count(client, created_profile_ids):
    before = len(client.get("/api/ink-profiles").json())

    created = _create(client)
    created_profile_ids.append(created["id"])

    assert created["name"] == "临时方案"
    assert created["is_default"] is False
    assert created["rules_json"]["page_overrides"] == {"3": {"roles": []}}

    after = client.get("/api/ink-profiles").json()
    assert len(after) == before + 1


def test_patch_set_default_is_exclusive(client, created_profile_ids):
    created = _create(client, "候选默认")
    created_profile_ids.append(created["id"])

    response = client.patch(f"/api/ink-profiles/{created['id']}", json={"is_default": True})
    assert response.status_code == 200, response.text
    assert response.json()["is_default"] is True

    items = client.get("/api/ink-profiles").json()
    assert [item["id"] for item in items if item["is_default"]] == [created["id"]]
    assert items[0]["id"] == created["id"]


def test_patch_replaces_rules_json(client, created_profile_ids):
    created = _create(client, "待改方案")
    created_profile_ids.append(created["id"])

    new_rules = {**VALID_RULES, "name": "改过的方案", "page_overrides": {"1": {"roles": []}}}
    response = client.patch(
        f"/api/ink-profiles/{created['id']}",
        json={"name": "改过的方案", "rules_json": new_rules},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "改过的方案"
    assert body["rules_json"] == new_rules


@pytest.mark.parametrize("rules", [{}, {"roles": []}, {"roles": "print"}, {"roles": None}])
def test_create_rejects_rules_without_roles(client, rules):
    response = client.post("/api/ink-profiles", json={"name": "坏方案", "rules_json": rules})
    assert response.status_code == 400
    assert "roles" in response.json()["detail"]


def test_patch_rejects_rules_without_roles(client, created_profile_ids):
    created = _create(client)
    created_profile_ids.append(created["id"])

    response = client.patch(f"/api/ink-profiles/{created['id']}", json={"rules_json": {"roles": []}})
    assert response.status_code == 400
    assert "roles" in response.json()["detail"]


def test_patch_unknown_profile_returns_404(client):
    response = client.patch("/api/ink-profiles/does-not-exist", json={"name": "x"})
    assert response.status_code == 404
    assert response.json()["detail"]
