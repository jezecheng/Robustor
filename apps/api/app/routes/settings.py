"""WP7 · 墨迹方案配置 + AI API 配置。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..ai_config import effective
from ..ai_probe import probe
from ..crypto import decrypt, encrypt
from ..db import get_session
from ..models import AiProvider, InkProfile
from ..schemas import (
    AiConfigOut,
    AiProviderIn,
    AiProviderOut,
    AiProviderPatch,
    AiProviderTestOut,
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


def _provider_out(provider: AiProvider) -> AiProviderOut:
    return AiProviderOut(
        id=provider.id,
        name=provider.name,
        base_url=provider.base_url,
        model=provider.model,
        has_key=bool(decrypt(provider.api_key)),
        is_active=provider.is_active,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


def _ai_config_out(session: Session) -> AiConfigOut:
    cfg = effective(session)
    providers = (
        session.query(AiProvider)
        .order_by(AiProvider.is_active.desc(), AiProvider.created_at)
        .all()
    )
    return AiConfigOut(
        providers=[_provider_out(p) for p in providers],
        active_provider_id=cfg["provider_id"],
        effective_provider=cfg["provider"],
        effective_base_url=cfg["base_url"],
        effective_model=cfg["model"],
        effective_api_key_set=bool(cfg["api_key"]),
        api_key_source=cfg["api_key_source"],
    )


def _clean_base_url(value: str) -> str:
    base_url = value.strip()
    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="base_url 需以 http:// 或 https:// 开头")
    return base_url


@router.get("/ai-config", response_model=AiConfigOut)
def read_ai_config(session: Session = Depends(get_session)) -> AiConfigOut:
    return _ai_config_out(session)


@router.post("/ai-providers", response_model=AiConfigOut, status_code=201)
def create_ai_provider(
    payload: AiProviderIn, session: Session = Depends(get_session)
) -> AiConfigOut:
    api_key = payload.api_key.strip()
    model = payload.model.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key 不能为空")
    if not model:
        raise HTTPException(status_code=400, detail="model 不能为空")

    count = session.query(AiProvider).count()
    name = payload.name.strip()[:128] or f"配置 {count + 1}"
    # 第一条配置自动设为使用中，避免新增后还要多点一次
    make_active = session.query(AiProvider).filter(AiProvider.is_active.is_(True)).count() == 0
    session.add(
        AiProvider(
            name=name,
            base_url=_clean_base_url(payload.base_url),
            model=model[:128],
            api_key=encrypt(api_key),
            is_active=make_active,
        )
    )
    session.commit()
    return _ai_config_out(session)


@router.patch("/ai-providers/{provider_id}", response_model=AiConfigOut)
def patch_ai_provider(
    provider_id: str, payload: AiProviderPatch, session: Session = Depends(get_session)
) -> AiConfigOut:
    provider = session.get(AiProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="配置不存在")

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name 不能为空")
        provider.name = name[:128]
    if payload.base_url is not None:
        provider.base_url = _clean_base_url(payload.base_url)
    if payload.model is not None:
        model = payload.model.strip()
        if not model:
            raise HTTPException(status_code=400, detail="model 不能为空")
        provider.model = model[:128]
    # 不传或留空都表示保持原 Key
    if payload.api_key:
        provider.api_key = encrypt(payload.api_key.strip())
    if payload.is_active is not None:
        if payload.is_active:
            session.query(AiProvider).filter(AiProvider.id != provider.id).update(
                {AiProvider.is_active: False}, synchronize_session=False
            )
        provider.is_active = payload.is_active

    session.commit()
    return _ai_config_out(session)


@router.post("/ai-providers/{provider_id}/test", response_model=AiProviderTestOut)
def test_ai_provider(
    provider_id: str, session: Session = Depends(get_session)
) -> AiProviderTestOut:
    provider = session.get(AiProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="配置不存在")

    api_key = decrypt(provider.api_key)
    if not api_key:
        return AiProviderTestOut(ok=False, latency_ms=0, message="未保存 Key 或 Key 无法解密")
    return AiProviderTestOut(
        **probe(
            provider.base_url,
            provider.model,
            api_key,
            session=session,
            provider_name=provider.name,
            provider_id=provider.id,
        )
    )


@router.delete("/ai-providers/{provider_id}", response_model=AiConfigOut)
def delete_ai_provider(
    provider_id: str, session: Session = Depends(get_session)
) -> AiConfigOut:
    provider = session.get(AiProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="配置不存在")
    session.delete(provider)
    session.commit()
    return _ai_config_out(session)
