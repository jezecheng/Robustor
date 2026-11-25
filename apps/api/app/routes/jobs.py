"""WP1 · 任务查询与重试（1 document : 1 job）。"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_session
from ..jobs import job_to_out, reset_for_retry, run_job
from ..models import Job
from ..schemas import JobOut

router = APIRouter(tags=["jobs"])


class RetryIn(BaseModel):
    from_stage: str = "preprocess"


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, session: Session = Depends(get_session)) -> JobOut:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job_to_out(job)


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
def retry_job(
    job_id: str,
    payload: RetryIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> JobOut:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    reset_for_retry(job, payload.from_stage)
    session.commit()
    background_tasks.add_task(run_job, job.id, payload.from_stage)
    return job_to_out(job)
