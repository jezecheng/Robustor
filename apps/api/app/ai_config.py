"""AI API 配置解析：数据库 > 环境变量 > 默认值。

每条 ai_provider 把名称 / Base URL / 模型 / Key 作为一个整体保存，同一时间只有一条
is_active（「使用中」）参与识别；没有任何使用中的配置时回落到环境变量 VLM_*。
读取发生在每次创建 OCR provider 时，因此页面保存后无需重启。
Key 只以密文落库，接口不再返回任何形式的 Key 内容。
"""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from .crypto import decrypt, encrypt, is_encrypted
from .models import AiConfig, AiKey, AiProvider

AI_CONFIG_ID = "default"
DEFAULT_BASE_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"
FALLBACK_NAME = "默认配置"


def get_row(session: Session) -> AiConfig | None:
    return session.get(AiConfig, AI_CONFIG_ID)


def active_provider(session: Session | None) -> AiProvider | None:
    if session is None:
        return None
    return session.query(AiProvider).filter(AiProvider.is_active.is_(True)).first()


def effective(session: Session | None = None) -> dict:
    """解析实际生效的配置。session 为 None 时只读环境变量（测试/无 DB 场景）。"""
    row = active_provider(session)
    env_key = os.environ.get("VLM_API_KEY", "")

    if row is not None:
        db_key = decrypt(row.api_key)
        api_key = db_key or env_key
        return {
            "provider": "vlm",
            "base_url": row.base_url or os.environ.get("VLM_BASE_URL", "") or DEFAULT_BASE_URL,
            "model": row.model or os.environ.get("VLM_MODEL", "") or DEFAULT_MODEL,
            "api_key": api_key,
            "api_key_source": "db" if db_key else "env" if env_key else "none",
            "provider_id": row.id,
            "provider_name": row.name or FALLBACK_NAME,
        }

    provider = os.environ.get("OCR_PROVIDER", "mock").lower()
    if provider not in ("mock", "vlm"):
        provider = "mock"
    return {
        "provider": provider,
        "base_url": os.environ.get("VLM_BASE_URL", "") or DEFAULT_BASE_URL,
        "model": os.environ.get("VLM_MODEL", "") or DEFAULT_MODEL,
        "api_key": env_key,
        "api_key_source": "env" if env_key else "none",
        "provider_id": None,
        "provider_name": "环境变量 Key" if env_key else FALLBACK_NAME,
    }


def migrate_and_secure(session: Session) -> None:
    """启动时执行（幂等）：

    1. 旧版 ai_config / ai_key 数据若存在且尚未迁移，合成一条 AiProvider；
    2. 把任何历史明文 Key 原地加密。
    """
    if session.query(AiProvider).count() == 0:
        cfg = get_row(session)
        keys = session.query(AiKey).order_by(AiKey.is_active.desc()).all()
        active = next((k for k in keys if k.is_active), keys[0] if keys else None)
        legacy_key = decrypt(active.api_key) if active and active.api_key else ""

        if cfg is not None or active is not None:
            session.add(
                AiProvider(
                    name=(active.name if active and active.name else FALLBACK_NAME),
                    base_url=(cfg.base_url if cfg and cfg.base_url else DEFAULT_BASE_URL),
                    model=(cfg.model if cfg and cfg.model else DEFAULT_MODEL),
                    api_key=encrypt(legacy_key),
                    is_active=bool(legacy_key),
                )
            )
            if cfg is not None:
                cfg.api_key = None

    changed = False
    for provider in session.query(AiProvider).all():
        if provider.api_key and not is_encrypted(provider.api_key):
            provider.api_key = encrypt(provider.api_key)
            changed = True
    # 旧表也可能残留明文 Key，一并加密，避免历史数据泄露
    for legacy in session.query(AiKey).all():
        if legacy.api_key and not is_encrypted(legacy.api_key):
            legacy.api_key = encrypt(legacy.api_key)
            changed = True
    if changed or session.new or session.dirty:
        session.commit()