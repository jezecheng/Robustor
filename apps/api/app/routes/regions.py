"""WP1 · 区域校对（校对台数据源）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Mark, ProblemImage, Region
from ..schemas import RegionMergeIn, RegionOut, RegionPatch

router = APIRouter(tags=["regions"])


def _get_region(session: Session, region_id: str) -> Region:
    region = session.get(Region, region_id)
    if region is None:
        raise HTTPException(status_code=404, detail="区域不存在")
    return region


def _to_out(region: Region) -> RegionOut:
    return RegionOut.model_validate(region)


@router.patch("/regions/{region_id}", response_model=RegionOut)
def patch_region(
    region_id: str, payload: RegionPatch, session: Session = Depends(get_session)
) -> RegionOut:
    region = _get_region(session, region_id)

    if payload.bbox is not None:
        if len(payload.bbox) != 4:
            raise HTTPException(status_code=400, detail="bbox 必须是 [x, y, w, h] 四个数")
        region.bbox = [min(1.0, max(0.0, float(value))) for value in payload.bbox]
    if payload.block_type is not None:
        region.block_type = payload.block_type
    if payload.page_start is not None:
        region.page_start = payload.page_start
    if payload.page_end is not None:
        region.page_end = payload.page_end

    if region.page_end < region.page_start:
        raise HTTPException(status_code=400, detail="page_end 不能小于 page_start")

    session.commit()
    return _to_out(region)


@router.post("/regions/merge", response_model=list[RegionOut])
def merge_regions(payload: RegionMergeIn, session: Session = Depends(get_session)) -> list[RegionOut]:
    ids = list(dict.fromkeys(payload.region_ids))
    regions = session.query(Region).filter(Region.id.in_(ids)).all()
    if len(regions) != len(ids):
        raise HTTPException(status_code=404, detail="存在无效的 region_id")

    if len({region.page_id for region in regions}) > 1:
        raise HTTPException(status_code=400, detail="只能合并同一页的区域")

    for region in regions:
        if len(region.bbox or []) != 4:
            raise HTTPException(status_code=400, detail="区域 bbox 数据不完整，无法合并")

    survivor = min(regions, key=lambda region: region.order_idx)
    xs = [float(region.bbox[0]) for region in regions]
    ys = [float(region.bbox[1]) for region in regions]
    rights = [float(region.bbox[0]) + float(region.bbox[2]) for region in regions]
    bottoms = [float(region.bbox[1]) + float(region.bbox[3]) for region in regions]
    left, top = max(0.0, min(xs)), max(0.0, min(ys))
    survivor.bbox = [
        left,
        top,
        min(1.0, max(rights)) - left,
        min(1.0, max(bottoms)) - top,
    ]
    survivor.block_type = "stem"
    survivor.page_start = min(region.page_start for region in regions)
    survivor.page_end = max(region.page_end for region in regions)

    removed_ids = [region.id for region in regions if region.id != survivor.id]
    if removed_ids:
        session.query(Mark).filter(Mark.region_id.in_(removed_ids)).delete(
            synchronize_session=False
        )
        session.query(Region).filter(Region.id.in_(removed_ids)).delete(synchronize_session=False)

    session.commit()
    session.refresh(survivor)
    return [_to_out(survivor)]


@router.delete("/regions/{region_id}", status_code=204)
def delete_region(region_id: str, session: Session = Depends(get_session)) -> None:
    region = _get_region(session, region_id)
    session.query(Mark).filter(Mark.region_id == region.id).delete(synchronize_session=False)
    session.query(ProblemImage).filter(ProblemImage.region_id == region.id).update(
        {ProblemImage.region_id: None}, synchronize_session=False
    )
    session.delete(region)
    session.commit()
