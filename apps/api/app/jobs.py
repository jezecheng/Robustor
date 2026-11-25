"""job 表读写 + 后台执行器。后台任务必须自建 Session，禁止复用请求 session。"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import Job
from .pipeline.orchestrator import STAGE_ORDER, run_pipeline
from .schemas import JobOut

logger = logging.getLogger(__name__)


def create_job(session: Session, document_id: str) -> Job:
    job = Job(document_id=document_id, stage="preprocess", status="queued", progress=0.0)
    session.add(job)
    session.commit()
    return job


def latest_job(session: Session, document_id: str) -> Job | None:
    """document : job = 1 : 1；按 created_at 取最新一条。"""
    return (
        session.query(Job)
        .filter(Job.document_id == document_id)
        .order_by(Job.created_at.desc())
        .first()
    )


def reset_for_retry(job: Job, from_stage: str = "preprocess") -> Job:
    job.status = "queued"
    job.stage = from_stage
    job.progress = 0.0
    job.error = None
    job.detail_json = "{}"
    return job


def job_to_out(job: Job) -> JobOut:
    try:
        detail = json.loads(job.detail_json or "{}")
    except json.JSONDecodeError:
        detail = {}
    return JobOut(
        id=job.id,
        document_id=job.document_id,
        stage=job.stage,
        status=job.status,
        progress=job.progress,
        detail=detail,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def run_job(job_id: str, from_stage: str = "preprocess") -> None:
    """FastAPI BackgroundTasks 入口。全程自建 session。"""
    start = from_stage if from_stage in STAGE_ORDER else "preprocess"
    session = SessionLocal()
    try:
        job = session.get(Job, job_id)
        if job is None:
            return
        job.status = "running"
        job.error = None
        session.commit()
        run_pipeline(session, job, start)
    except Exception as exc:  # noqa: BLE001 - 必须兜底写 failed
        logger.exception("pipeline failed: job=%s", job_id)
        session.rollback()
        job = session.get(Job, job_id)
        if job is not None:
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"[:500]
            session.commit()
    finally:
        session.close()
