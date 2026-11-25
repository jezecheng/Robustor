"""WP3 识别测试：mock provider 下跑 layout→ink→recognize，并校验 provider 降级与符号映射。

数据库由 conftest 的 RB_DATA_DIR / RB_DB_PATH 隔离；本模块只用 ORM + Storage，
不经过 HTTP，也不需要启动服务器。
"""

from __future__ import annotations

import pytest

from app.config import FIXTURE_DEMO_DIR
from app.db import SessionLocal, init_db
from app.models import Document, Mark, Page, Region
from app.pipeline.base import StageContext
from app.pipeline.orchestrator import STAGES
from app.pipeline.providers.mock import MockOcrProvider
from app.pipeline.providers.register import get_ocr_provider
from app.pipeline.s4_recognize import symbol_to_verdict
from app.storage import Storage

VERDICTS = {"right", "wrong", "partial", "unknown"}
TEXT_TYPES = {"stem", "answer", "correction"}


@pytest.fixture()
def session():
    init_db()
    with SessionLocal() as db:
        yield db


def _make_page(db, storage: Storage) -> tuple[Document, Page]:
    doc = Document(subject="math", source_name="p1.jpg")
    db.add(doc)
    db.commit()
    rel, width, height = storage.save_page(
        doc.id, 1, (FIXTURE_DEMO_DIR / "p1.jpg").read_bytes()
    )
    page = Page(
        document_id=doc.id,
        idx=1,
        image_path=rel,
        width=width,
        height=height,
        status="pending",
    )
    db.add(page)
    db.commit()
    return doc, page


def _run_stage(db, doc: Document, page: Page, storage: Storage, name: str):
    stage = STAGES[name]
    ctx = StageContext(doc.id, page.id, db, storage, {"ink_profile": {}})
    result = stage.run(ctx)
    assert result.ok, result.warnings
    return result


@pytest.fixture()
def env(session, monkeypatch):
    monkeypatch.setenv("OCR_PROVIDER", "mock")
    monkeypatch.delenv("VLM_API_KEY", raising=False)
    storage = Storage()
    doc, page = _make_page(session, storage)
    yield session, doc, page, storage
    # 清理本用例产生的行，避免影响同库的其他测试（如 documents 列表为空）
    doc_id, page_id = doc.id, page.id
    region_ids = [
        row[0] for row in session.query(Region.id).filter(Region.page_id == page_id).all()
    ]
    if region_ids:
        session.query(Mark).filter(Mark.region_id.in_(region_ids)).delete(
            synchronize_session=False
        )
    session.query(Region).filter(Region.page_id == page_id).delete(synchronize_session=False)
    session.query(Page).filter(Page.id == page_id).delete(synchronize_session=False)
    session.query(Document).filter(Document.id == doc_id).delete(synchronize_session=False)
    session.commit()


@pytest.fixture()
def pipeline(env):
    db, doc, page, storage = env
    for name in ("layout", "ink"):
        _run_stage(db, doc, page, storage, name)
    result = _run_stage(db, doc, page, storage, "recognize")
    return db, doc, page, storage, result


def test_recognize_mock_pipeline(pipeline):
    db, _doc, page, _storage, result = pipeline
    regions = db.query(Region).filter(Region.page_id == page.id).all()

    text_regions = [r for r in regions if r.block_type in TEXT_TYPES]
    filled = [r for r in text_regions if (r.text or "").strip()]
    assert len(filled) >= 3
    assert all(0.0 <= r.confidence <= 1.0 for r in text_regions)

    region_ids = [r.id for r in regions]
    marks = db.query(Mark).filter(Mark.region_id.in_(region_ids)).all()
    assert len(marks) >= 1
    assert all(m.verdict in VERDICTS for m in marks)
    assert all(m.problem_id is None for m in marks)

    assert result.stats["regions"] == len(regions)
    assert result.stats["recognized"] >= 3
    assert result.stats["marks"] == len(marks)
    assert result.stats["provider"] == "mock"


def test_recognize_fills_empty_text_and_saves_crop(pipeline):
    db, doc, page, storage, _result = pipeline
    region = (
        db.query(Region)
        .filter(Region.page_id == page.id, Region.block_type == "stem")
        .first()
    )
    assert region is not None
    region.text = ""
    region.confidence = 0.0
    db.commit()

    _run_stage(db, doc, page, storage, "recognize")
    db.refresh(region)
    assert (region.text or "").strip()
    assert 0.0 <= region.confidence <= 1.0
    # crop 必须落盘，且文件名以 region id 为前缀
    assert storage.abs(f"media/crops/{region.id[:8]}_ocr.jpg").is_file()


def test_recognize_is_idempotent_for_marks(pipeline):
    db, doc, page, storage, _result = pipeline
    region_ids = [
        row[0] for row in db.query(Region.id).filter(Region.page_id == page.id).all()
    ]

    def mark_count() -> int:
        return db.query(Mark).filter(Mark.region_id.in_(region_ids)).count()

    first = mark_count()
    _run_stage(db, doc, page, storage, "recognize")
    assert mark_count() == first


def test_provider_falls_back_to_mock_without_key(monkeypatch):
    monkeypatch.delenv("VLM_API_KEY", raising=False)
    monkeypatch.delenv("OCR_PROVIDER", raising=False)
    assert isinstance(get_ocr_provider(), MockOcrProvider)

    monkeypatch.setenv("OCR_PROVIDER", "vlm")
    assert isinstance(get_ocr_provider(), MockOcrProvider)


def test_provider_uses_vlm_when_key_present(monkeypatch):
    monkeypatch.setenv("OCR_PROVIDER", "vlm")
    monkeypatch.setenv("VLM_API_KEY", "test-key")
    assert get_ocr_provider().name == "vlm"


@pytest.mark.parametrize(
    ("symbol", "verdict"),
    [
        ("✓", "right"),
        ("√", "right"),
        ("V", "right"),
        ("✗", "wrong"),
        ("×", "wrong"),
        ("x", "wrong"),
        ("X", "wrong"),
        ("△", "partial"),
        ("半", "partial"),
        ("+", "partial"),
        ("-", "partial"),
        ("5/10", "partial"),
        ("1/2 分", "partial"),
        ("", "unknown"),
        ("?", "unknown"),
    ],
)
def test_symbol_to_verdict(symbol, verdict):
    assert symbol_to_verdict(symbol) == verdict
