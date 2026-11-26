"""SQLAlchemy engine / session。测试通过 RB_DB_PATH 指向临时文件。"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import DB_PATH
from .models import Base

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)

# 知识图谱字段：老库无 alembic，启动时按需 ALTER TABLE 补齐。
TAG_COLUMNS: tuple[tuple[str, str], ...] = (
    ("external_id", "VARCHAR(64)"),
    ("subject", "VARCHAR(16)"),
    ("domain", "VARCHAR(32)"),
    ("grade", "INTEGER"),
    ("semester", "VARCHAR(8)"),
    ("chapter", "VARCHAR(255)"),
    ("topic_type", "VARCHAR(16)"),
    ("description", "TEXT"),
    ("mastery_json", "JSON"),
    ("diagnostic_json", "JSON"),
    ("standards_json", "JSON"),
)


def _migrate_tag_columns() -> None:
    with engine.begin() as conn:
        existing = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(tag)")}
        for name, ddl in TAG_COLUMNS:
            if name not in existing:
                conn.exec_driver_sql(f"ALTER TABLE tag ADD COLUMN {name} {ddl}")
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_tag_external_id ON tag(external_id)"
        )


def init_db() -> None:
    Base.metadata.create_all(engine)
    _migrate_tag_columns()
    from .ai_config import migrate_and_secure

    with SessionLocal() as session:
        migrate_and_secure(session)


def get_session() -> Iterator[Session]:
    """FastAPI 依赖注入用。后台任务禁止使用它，必须自建 SessionLocal()。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
