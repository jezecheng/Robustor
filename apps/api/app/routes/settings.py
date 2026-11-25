"""WP7 · 墨迹方案配置 + AI API 配置。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..ai_config import AI_CONFIG_ID, effective, get_row, mask_key
from ..crypto import decrypt, encrypt
from ..db import get_session
from ..models import AiConfig, AiKey, InkProfile
from ..schemas import (
    AiConfigOut,
    AiConfigPatch,
    AiKeyIn,
    AiKeyOut,
    AiKeyPatch,
    InkProfileIn,
    InkProfileOut,
    InkProfilePatch,
)

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


# ---------------------------------------------------------------- AI API 配置


def _key_out(key: AiKey) -> AiKeyOut:
    return AiKeyOut(
        id=key.id,
        name=key.name,
        api_key_masked=mask_key(decrypt(key.api_key)),
        is_active=key.is_active,
        created_at=key.created_at,
    )


def _ai_config_out(session: Session, row: AiConfig | None = None) -> AiConfigOut:
    row = row if row is not None else get_row(session)
    cfg = effective(session)
    keys = (
        session.query(AiKey)
        .order_by(AiKey.is_active.desc(), AiKey.created_at)
        .all()
    )
    return AiConfigOut(
        provider=row.provider if row else None,
        base_url=row.base_url if row else None,
        model=row.model if row else None,
        updated_at=row.updated_at if row else None,
        keys=[_key_out(key) for key in keys],
        effective_provider=cfg["provider"],
        effective_base_url=cfg["base_url"],
        effective_model=cfg["model"],
        effective_api_key_set=bool(cfg["api_key"]),
        api_key_source=cfg["api_key_source"],
        active_key_id=cfg["key_id"],
    )


@router.get("/ai-config", response_model=AiConfigOut)
def read_ai_config(session: Session = Depends(get_session)) -> AiConfigOut:
    return _ai_config_out(session)


@router.put("/ai-config", response_model=AiConfigOut)
def update_ai_config(
    payload: AiConfigPatch, session: Session = Depends(get_session)
) -> AiConfigOut:
    """整表覆盖：显式传 null 的字段表示清除（回落 env/默认值）。"""
    row = get_row(session) or AiConfig(id=AI_CONFIG_ID)
    fields = payload.model_fields_set

    if "provider" in fields:
        row.provider = payload.provider

    if "base_url" in fields:
        base_url = (payload.base_url or "").strip()
        if base_url and not base_url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="base_url 需以 http:// 或 https:// 开头")
        row.base_url = base_url or None

    if "model" in fields:
        row.model = (payload.model or "").strip() or None

    session.add(row)
    session.commit()
    session.refresh(row)
    return _ai_config_out(session, row)


# ---------------------------------------------------------------- AI API Key 池


def _deactivate_others(session: Session, keep_id: str) -> None:
    session.query(AiKey).filter(AiKey.id != keep_id).update(
        {AiKey.is_active: False}, synchronize_session=False
    )


@router.get("/ai-keys", response_model=list[AiKeyOut])
def list_ai_keys(session: Session = Depends(get_session)) -> list[AiKeyOut]:
    keys = session.query(AiKey).order_by(AiKey.is_active.desc(), AiKey.created_at).all()
    return [_key_out(key) for key in keys]


@router.post("/ai-keys", response_model=AiKeyOut, status_code=201)
def create_ai_key(payload: AiKeyIn, session: Session = Depends(get_session)) -> AiKeyOut:
    api_key = payload.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key 不能为空")
    name = payload.name.strip() or f"Key {session.query(AiKey).count() + 1}"
    # 第一条 Key 自动激活，避免新增后还要多点一次
    make_active = session.query(AiKey).filter(AiKey.is_active.is_(True)).count() == 0
    key = AiKey(name=name[:128], api_key=encrypt(api_key), is_active=make_active)
    session.add(key)
    session.commit()
    session.refresh(key)
    return _key_out(key)


@router.patch("/ai-keys/{key_id}", response_model=AiKeyOut)
def patch_ai_key(
    key_id: str, payload: AiKeyPatch, session: Session = Depends(get_session)
) -> AiKeyOut:
    key = session.get(AiKey, key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="Key 不存在")

    if payload.name is not None:
        key.name = payload.name.strip()[:128] or key.name
    if payload.api_key is not None:
        api_key = payload.api_key.strip()
        if not api_key:
            raise HTTPException(status_code=400, detail="api_key 不能为空")
        key.api_key = encrypt(api_key)
    if payload.is_active is not None:
        if payload.is_active:
            _deactivate_others(session, key.id)
        key.is_active = payload.is_active

    session.commit()
    session.refresh(key)
    return _key_out(key)


@router.delete("/ai-keys/{key_id}", status_code=204)
def delete_ai_key(key_id: str, session: Session = Depends(get_session)) -> None:
    key = session.get(AiKey, key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="Key 不存在")
    session.delete(key)
    session.commit()
