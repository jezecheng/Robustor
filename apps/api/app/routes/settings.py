"""WP7 · 墨迹方案配置。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import InkProfile
from ..schemas import InkProfileIn, InkProfileOut, InkProfilePatch

router = APIRouter(tags=["settings"])


def _out(profile: InkProfile) -> InkProfileOut:
    return InkProfileOut.model_validate(profile)


def _validate_rules_json(rules_json: dict[str, Any] | None) -> dict[str, Any]:
    """rules_json 至少要有一个角色规则，否则 s3 分色无从下手。"""
    rules = rules_json or {}
    roles = rules.get("roles")
    if not isinstance(roles, list) or not roles:
        raise HTTPException(
            status_code=400,
            detail="rules_json.roles 必须是非空数组（至少包含一个角色规则）",
        )
    return rules


def _clear_default(session: Session, keep_id: str | None = None) -> None:
    query = session.query(InkProfile).filter(InkProfile.is_default.is_(True))
    if keep_id is not None:
        query = query.filter(InkProfile.id != keep_id)
    query.update({InkProfile.is_default: False}, synchronize_session=False)


@router.get("/ink-profiles", response_model=list[InkProfileOut])
def list_ink_profiles(session: Session = Depends(get_session)) -> list[InkProfileOut]:
    rows = (
        session.query(InkProfile)
        .order_by(InkProfile.is_default.desc(), InkProfile.name)
        .all()
    )
    return [_out(row) for row in rows]


@router.post("/ink-profiles", response_model=InkProfileOut, status_code=201)
def create_ink_profile(
    payload: InkProfileIn, session: Session = Depends(get_session)
) -> InkProfileOut:
    rules_json = _validate_rules_json(payload.rules_json)
    if payload.is_default:
        _clear_default(session)
    profile = InkProfile(name=payload.name, is_default=payload.is_default, rules_json=rules_json)
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return _out(profile)


@router.patch("/ink-profiles/{profile_id}", response_model=InkProfileOut)
def patch_ink_profile(
    profile_id: str, payload: InkProfilePatch, session: Session = Depends(get_session)
) -> InkProfileOut:
    profile = session.get(InkProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="墨迹方案不存在")

    if payload.name is not None:
        profile.name = payload.name
    if payload.rules_json is not None:
        profile.rules_json = _validate_rules_json(payload.rules_json)
    if payload.is_default is not None:
        if payload.is_default:
            _clear_default(session, keep_id=profile.id)
        profile.is_default = payload.is_default

    session.commit()
    session.refresh(profile)
    return _out(profile)
