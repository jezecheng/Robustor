from __future__ import annotations

from typing import NamedTuple, Protocol

from sqlalchemy.orm import Session

from ..storage import Storage


class StageContext(NamedTuple):
    document_id: str
    page_id: str | None  # 页级阶段有值；文档级阶段为 None
    session: Session
    storage: Storage
    config: dict


class StageResult(NamedTuple):
    ok: bool
    warnings: list[str]
    stats: dict


class Stage(Protocol):
    name: str

    def run(self, ctx: StageContext) -> StageResult: ...


def ok_result(**stats) -> StageResult:
    return StageResult(ok=True, warnings=[], stats=stats)


def fail_result(message: str, **stats) -> StageResult:
    return StageResult(ok=False, warnings=[message], stats=stats)
