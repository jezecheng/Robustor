"""AI API 配置解析：数据库 > 环境变量 > 默认值。

Key 存在 ai_key 表中，可有多条，is_active 为 true 的那条参与识别；没有激活 Key 时回落到
环境变量 VLM_API_KEY。读取发生在每次创建 OCR provider 时，因此页面保存后无需重启。
本模块只对外暴露是否配置与掩码，不返回明文。
"""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from .crypto import decrypt, encrypt, is_encrypted
from .models import AiConfig, AiKey

AI_CONFIG_ID = "default"
DEFAULT_BASE_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"


def get_row(session: Session) -> AiConfig | None:
    return session.get(AiConfig, AI_CONFIG_ID)


def active_key(session: Session) -> AiKey | None:
    return session.query(AiKey).filter(AiKey.is_active.is_(True)).first()


def mask_key(key: str) -> str:
    """只露头尾，短 key 全掩码。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:3]}****{key[-4:]}"


def effective(session: Session | None = None) -> dict:
    """解析实际生效的配置。session 为 None 时只读环境变量（测试/无 DB 场景）。"""
    row = get_row(session) if session is not None else None
    key_row = active_key(session) if session is not None else None

    provider = (row.provider if row and row.provider else os.environ.get("OCR_PROVIDER", "mock")).lower()
    if provider not in ("mock", "vlm"):
        provider = "mock"

    db_key = decrypt(key_row.api_key) if key_row else ""
    env_key = os.environ.get("VLM_API_KEY", "")
    api_key = db_key or env_key
    key_source = "db" if db_key else "env" if env_key else "none"

    base_url = (
        (row.base_url if row and row.base_url else "")
        or os.environ.get("VLM_BASE_URL", "")
        or DEFAULT_BASE_URL
    )
    model = (
        (row.model if row and row.model else "")
        or os.environ.get("VLM_MODEL", "")
        or DEFAULT_MODEL
    )

    return {
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
        "api_key_source": key_source,
        "key_id": key_row.id if key_row else None,
    }


def migrate_legacy_key(session: Session) -> None:
    """把旧版 ai_config.api_key 搬进 ai_key 表并加密，只搬一次。"""
    row = get_row(session)
    legacy = row.api_key if row and row.api_key else ""
    if not legacy:
        return
    if session.query(AiKey).count() == 0:
        session.add(AiKey(name="默认 Key", api_key=encrypt(legacy), is_active=True))
    row.api_key = None
    session.commit()


def encrypt_plaintext_keys(session: Session) -> None:
    """把历史明文 Key 原地加密（幂等）。"""
    changed = False
    for key in session.query(AiKey).all():
        if key.api_key and not is_encrypted(key.api_key):
            key.api_key = encrypt(key.api_key)
            changed = True
    if changed:
        session.commit()
