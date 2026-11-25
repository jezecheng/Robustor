"""阶段编排：串 6 个 stage、写 job 进度、异常上抛给 jobs.run_job 兜底。

WP1 拥有本文件，可在此基础上加断点重跑细节。
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from ..models import Document, InkProfile, Job, Page
from ..storage import Storage
from . import s1_preprocess, s2_layout, s3_ink, s4_recognize, s5_assemble, s6_tag
from .base import Stage, StageContext

STAGE_ORDER: list[str] = ["preprocess", "layout", "ink", "recognize", "assemble", "tag"]
PAGE_LEVEL = {"preprocess", "layout", "ink", "recognize"}

STAGES: dict[str, Stage] = {
    "preprocess": s1_preprocess.STAGE,
    "layout": s2_layout.STAGE,
    "ink": s3_ink.STAGE,
    "recognize": s4_recognize.STAGE,
    "assemble": s5_assemble.STAGE,
    "tag": s6_tag.STAGE,
}


def load_config(session: Session) -> dict:
    profile = session.query(InkProfile).filter(InkProfile.is_default.is_(True)).first()
    return {"ink_profile": profile.rules_json if profile else {}}


def run_pipeline(session: Session, job: Job, from_stage: str = "preprocess") -> Job:
    document = session.get(Document, job.document_id)
    if document is None:
        raise RuntimeError(f"document {job.document_id} not found")

    start = STAGE_ORDER.index(from_stage) if from_stage in STAGE_ORDER else 0
    config = load_config(session)
    storage = Storage()
    total = len(STAGE_ORDER)

    for pos in range(start, total):
        name = STAGE_ORDER[pos]
        job.stage = name
        job.status = "running"
        job.progress = round(pos / total, 3)
        job.error = None
        session.commit()

        stage = STAGES[name]
        warnings: list[str] = []
        stats: dict = {}

        if name in PAGE_LEVEL:
            pages = (
                session.query(Page)
                .filter(Page.document_id == document.id)
                .order_by(Page.idx)
                .all()
            )
            if not pages:
                raise RuntimeError("document has no pages")
            for i, page in enumerate(pages):
                ctx = StageContext(document.id, page.id, session, storage, config)
                result = stage.run(ctx)
                if not result.ok:
                    page.status = "failed"
                    session.commit()
                    raise RuntimeError(f"{name} failed on page {page.idx}: {'; '.join(result.warnings)}")
                warnings.extend(result.warnings)
                stats[f"p{page.idx}"] = result.stats
                # 页级阶段按页推进进度，前端 1s 轮询能看到连续变化
                job.progress = round((pos + (i + 1) / len(pages)) / total, 3)
                session.commit()
        else:
            ctx = StageContext(document.id, None, session, storage, config)
            result = stage.run(ctx)
            if not result.ok:
                raise RuntimeError(f"{name} failed: {'; '.join(result.warnings)}")
            warnings.extend(result.warnings)
            stats["document"] = result.stats

        job.progress = round((pos + 1) / total, 3)
        job.detail_json = json.dumps(
            {"stage": name, "warnings": warnings, "stats": stats}, ensure_ascii=False
        )
        session.commit()

    job.status = "done"
    job.progress = 1.0
    session.commit()
    return job
