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


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI 依赖注入用。后台任务禁止使用它，必须自建 SessionLocal()。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
