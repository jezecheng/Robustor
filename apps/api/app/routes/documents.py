"""WP1 · 文档上传 / 查询 / 级联删除。"""

from __future__ import annotations

import shutil

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_session
from ..jobs import create_job, job_to_out, latest_job, run_job
from ..models import Document, Job, Mark, Page, Problem, ProblemImage, ProblemTag, Region, Review, Solution
from ..schemas import (
    DocumentCreated,
    DocumentListItem,
    DocumentOut,
    JobOut,
    PageOut,
    RegionOut,
)
from ..storage import Storage

router = APIRouter(tags=["documents"])


def _page_out(page: Page, region_count: int) -> PageOut:
    return PageOut(
        id=page.id,
        document_id=page.document_id,
        idx=page.idx,
        image_path=page.image_path,
        width=page.width,
        height=page.height,
        rotation=page.rotation,
        status=page.status,
        region_count=region_count,
    )


@router.post("/documents", response_model=DocumentCreated, status_code=201)
async def create_document(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] | None = File(default=None),
    subject: str = Form("math"),
    session: Session = Depends(get_session),
) -> DocumentCreated:
    uploads = files or []
    if not uploads:
        raise HTTPException(status_code=400, detail="至少上传一张图片（字段名 files）")

    document = Document(
        subject=subject,
        source_name=uploads[0].filename or "",
        page_count=len(uploads),
    )
    session.add(document)
    session.flush()

    storage = Storage()
    for idx, upload in enumerate(uploads, start=1):
        data = await upload.read()
        if not data:
            raise HTTPException(status_code=400, detail=f"文件 {upload.filename or idx} 为空")
        try:
            rel, width, height = storage.save_page(document.id, idx, data)
        except Exception as exc:  # noqa: BLE001 - 任意图片解析失败都按 400 返回
            session.rollback()
            raise HTTPException(
                status_code=400, detail=f"无法解析图片 {upload.filename or idx}: {exc}"
            ) from exc
        session.add(
            Page(
                document_id=document.id,
                idx=idx,
                image_path=rel,
                width=width,
                height=height,
                status="pending",
            )
        )

    session.commit()
    job = create_job(session, document.id)
    background_tasks.add_task(run_job, job.id)
    return DocumentCreated(document_id=document.id, job_id=job.id)


@router.get("/documents", response_model=list[DocumentListItem])
def list_documents(session: Session = Depends(get_session)) -> list[DocumentListItem]:
    documents = session.query(Document).order_by(Document.created_at.desc()).all()
    return [
        DocumentListItem(
            id=document.id,
            subject=document.subject,
            source_name=document.source_name,
            page_count=document.page_count,
            created_at=document.created_at,
            problem_count=session.query(Problem)
            .filter(Problem.document_id == document.id)
            .count(),
        )
        for document in documents
    ]


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, session: Session = Depends(get_session)) -> DocumentOut:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    counts = dict(
        session.query(Region.page_id, func.count(Region.id))
        .filter(Region.document_id == document_id)
        .group_by(Region.page_id)
        .all()
    )
    pages = (
        session.query(Page)
        .filter(Page.document_id == document_id)
        .order_by(Page.idx)
        .all()
    )
    job = latest_job(session, document_id)
    return DocumentOut(
        id=document.id,
        subject=document.subject,
        source_name=document.source_name,
        page_count=document.page_count,
        created_at=document.created_at,
        pages=[_page_out(page, counts.get(page.id, 0)) for page in pages],
        job=job_to_out(job) if job is not None else None,
    )


def _unlink(storage: Storage, rel: str) -> None:
    if not rel:
        return
    try:
        storage.abs(rel).unlink(missing_ok=True)
    except OSError:
        pass


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: str, session: Session = Depends(get_session)) -> None:
    if session.get(Document, document_id) is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    problem_ids = [
        row[0]
        for row in session.query(Problem.id).filter(Problem.document_id == document_id).all()
    ]
    region_ids = [
        row[0]
        for row in session.query(Region.id).filter(Region.document_id == document_id).all()
    ]

    image_paths: list[str] = []
    if problem_ids:
        session.query(Mark).filter(Mark.problem_id.in_(problem_ids)).delete(
            synchronize_session=False
        )
        session.query(ProblemTag).filter(ProblemTag.problem_id.in_(problem_ids)).delete(
            synchronize_session=False
        )
        session.query(Review).filter(Review.problem_id.in_(problem_ids)).delete(
            synchronize_session=False
        )
        session.query(Solution).filter(Solution.problem_id.in_(problem_ids)).delete(
            synchronize_session=False
        )
        image_paths = [
            row[0]
            for row in session.query(ProblemImage.image_path)
            .filter(ProblemImage.problem_id.in_(problem_ids))
            .all()
        ]
        session.query(ProblemImage).filter(ProblemImage.problem_id.in_(problem_ids)).delete(
            synchronize_session=False
        )
    if region_ids:
        session.query(Mark).filter(Mark.region_id.in_(region_ids)).delete(
            synchronize_session=False
        )

    session.query(Region).filter(Region.document_id == document_id).delete(
        synchronize_session=False
    )
    session.query(Problem).filter(Problem.document_id == document_id).delete(
        synchronize_session=False
    )
    session.query(Page).filter(Page.document_id == document_id).delete(synchronize_session=False)
    session.query(Job).filter(Job.document_id == document_id).delete(synchronize_session=False)
    session.query(Document).filter(Document.id == document_id).delete(synchronize_session=False)
    session.commit()

    storage = Storage()
    shutil.rmtree(storage.abs(f"media/pages/{document_id}"), ignore_errors=True)
    for rel in image_paths:
        _unlink(storage, rel)
    for region_id in region_ids:
        _unlink(storage, f"media/crops/ocr_{region_id[:8]}.jpg")


@router.get("/documents/{document_id}/job", response_model=JobOut)
def get_latest_job(document_id: str, session: Session = Depends(get_session)) -> JobOut:
    if session.get(Document, document_id) is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    job = latest_job(session, document_id)
    if job is None:
        raise HTTPException(status_code=404, detail="该文档还没有任务")
    return job_to_out(job)


@router.get("/documents/{document_id}/regions", response_model=list[RegionOut])
def list_regions(document_id: str, session: Session = Depends(get_session)) -> list[RegionOut]:
    if session.get(Document, document_id) is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    rows = (
        session.query(Region)
        .join(Page, Page.id == Region.page_id)
        .filter(Region.document_id == document_id)
        .order_by(Page.idx, Region.order_idx)
        .all()
    )
    return [RegionOut.model_validate(row) for row in rows]
