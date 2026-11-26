from datetime import datetime

import pytest

from app.db import SessionLocal
from app.models import AiUsageLog
from app.usage import usage_counts


@pytest.fixture()
def usage_rows():
    session = SessionLocal()
    session.query(AiUsageLog).delete()
    session.add_all(
        [
            AiUsageLog(
                created_at=datetime(2026, 1, 5, 10, 0, 0),
                scene="OCR 识别",
                provider_name="Key A",
                model="vlm-1",
                success=True,
                latency_ms=120,
                prompt_tokens=100,
                completion_tokens=50,
                reasoning_tokens=20,
                cached_tokens=30,
                total_tokens=150,
            ),
            AiUsageLog(
                created_at=datetime(2026, 1, 5, 12, 0, 0),
                scene="知识点打标",
                provider_name="Key B",
                model="chat-1",
                success=False,
                error="HTTP 500",
                latency_ms=80,
                prompt_tokens=0,
                completion_tokens=0,
                reasoning_tokens=0,
                cached_tokens=0,
                total_tokens=0,
            ),
            AiUsageLog(
                created_at=datetime(2026, 1, 7, 2, 0, 0),
                scene="OCR 识别",
                provider_name="Key A",
                model="vlm-1",
                success=True,
                latency_ms=200,
                prompt_tokens=200,
                completion_tokens=100,
                reasoning_tokens=0,
                cached_tokens=0,
                total_tokens=300,
            ),
        ]
    )
    session.commit()
    session.close()
    yield
    session = SessionLocal()
    session.query(AiUsageLog).delete()
    session.commit()
    session.close()


START = "2026-01-04T16:00:00Z"  # 东八区 2026-01-05 00:00
END = "2026-01-07T15:59:59Z"  # 东八区 2026-01-07 23:59:59


def test_summary_buckets_and_totals(client, usage_rows):
    response = client.get(
        "/api/ai-usage/summary", params={"start": START, "end": END, "bucket": "day"}
    )
    assert response.status_code == 200
    data = response.json()

    totals = data["totals"]
    assert totals["requests"] == 3
    assert totals["success"] == 2
    assert totals["failed"] == 1
    assert totals["success_rate"] == pytest.approx(2 / 3, abs=1e-3)
    assert totals["prompt_tokens"] == 300
    assert totals["completion_tokens"] == 150
    assert totals["reasoning_tokens"] == 20
    assert totals["cached_tokens"] == 30
    assert totals["total_tokens"] == 450

    assert [row["bucket"] for row in data["series"]] == [
        "2026-01-05",
        "2026-01-06",
        "2026-01-07",
    ]
    first = data["series"][0]
    assert first["requests"] == 2
    assert first["failed"] == 1
    assert first["prompt_tokens"] == 100
    assert data["series"][1]["requests"] == 0
    assert data["series"][2]["total_tokens"] == 300

    scenes = {item["value"]: item for item in data["scenes"]}
    assert scenes["OCR 识别"]["requests"] == 2
    assert scenes["知识点打标"]["requests"] == 1
    providers = {item["value"]: item for item in data["providers"]}
    assert providers["Key A"]["total_tokens"] == 450
    models = {item["value"]: item for item in data["models"]}
    assert models["vlm-1"]["requests"] == 2


def test_summary_empty_range(client, usage_rows):
    response = client.get(
        "/api/ai-usage/summary",
        params={"start": "2026-03-01T00:00:00Z", "end": "2026-03-02T23:59:59Z", "bucket": "day"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["totals"]["requests"] == 0
    assert data["totals"]["success_rate"] == 0
    assert len(data["series"]) == 3
    assert data["scenes"] == []


def test_requests_pagination_and_filter(client, usage_rows):
    response = client.get(
        "/api/ai-usage/requests",
        params={"start": START, "end": END, "page": 1, "size": 2},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["items"][0]["scene"] == "OCR 识别"
    assert data["items"][0]["total_tokens"] == 300
    assert data["items"][0]["created_at"].startswith("2026-01-07")
    assert data["items"][1]["success"] is False
    assert data["items"][1]["error"] == "HTTP 500"

    page2 = client.get(
        "/api/ai-usage/requests",
        params={"start": START, "end": END, "page": 2, "size": 2},
    ).json()
    assert len(page2["items"]) == 1
    assert page2["items"][0]["scene"] == "OCR 识别"
    assert page2["items"][0]["prompt_tokens"] == 100

    failed = client.get(
        "/api/ai-usage/requests",
        params={"start": START, "end": END, "success": "false"},
    ).json()
    assert failed["total"] == 1


def test_usage_hook_records_provider_metadata(client):
    from app.pipeline.providers.register import _usage_hook

    session = SessionLocal()
    session.query(AiUsageLog).delete()
    session.commit()

    hook = _usage_hook(
        session,
        "OCR 识别",
        {"provider_id": "prov-1", "provider_name": "视觉 Key A", "model": "vlm-1"},
        "doc-1",
    )
    assert hook is not None
    hook(
        {
            "success": True,
            "error": None,
            "latency_ms": 42,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
    )

    row = session.query(AiUsageLog).one()
    assert row.scene == "OCR 识别"
    assert row.provider_id == "prov-1"
    assert row.provider_name == "视觉 Key A"
    assert row.model == "vlm-1"
    assert row.document_id == "doc-1"
    assert row.total_tokens == 15
    session.query(AiUsageLog).delete()
    session.commit()
    session.close()


def test_chat_provider_reports_usage(monkeypatch):
    from app.pipeline.providers import chat

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            }

    monkeypatch.setattr(chat.httpx, "post", lambda *args, **kwargs: FakeResponse())
    events: list[dict] = []
    provider = chat.ChatProvider(
        api_key="test-key",
        base_url="http://example.test/v1",
        model="chat-1",
        on_usage=events.append,
    )

    assert provider.complete_json("system", "user") == {"ok": True}
    assert events[0]["success"] is True
    assert events[0]["usage"]["completion_tokens"] == 7

    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(chat.httpx, "post", boom)
    with pytest.raises(RuntimeError):
        provider.complete_json("system", "user")
    assert events[1]["success"] is False
    assert "network down" in events[1]["error"]


def test_usage_counts_supports_provider_variants():
    assert usage_counts(None)["total_tokens"] == 0

    openai = usage_counts(
        {
            "prompt_tokens": 100,
            "completion_tokens": 40,
            "prompt_tokens_details": {"cached_tokens": 60},
            "completion_tokens_details": {"reasoning_tokens": 10},
        }
    )
    assert openai == {
        "prompt_tokens": 100,
        "completion_tokens": 40,
        "reasoning_tokens": 10,
        "cached_tokens": 60,
        "total_tokens": 140,
    }

    deepseek = usage_counts(
        {"prompt_tokens": 50, "completion_tokens": 20, "prompt_cache_hit_tokens": 30}
    )
    assert deepseek["cached_tokens"] == 30
    assert deepseek["total_tokens"] == 70
