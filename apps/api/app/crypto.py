"""API Key 静态加密：数据库只存 Fernet 密文，明文仅在内存中短暂存在。

主密钥来源（二选一）：
1. 环境变量 RB_SECRET_KEY：可填 Fernet key（32 字节 urlsafe base64），也可填任意口令，
   口令会经 SHA-256 派生；生产环境推荐显式配置，便于多实例共用。
2. 未配置时自动在 data/secret.key 生成并持久化（权限 600），随 data 卷一起保留。

更换主密钥会导致旧密文无法解密，此时按未配置处理（识别回落 mock），不会让服务崩溃。
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

from .config import DATA_DIR

PREFIX = "enc:v1:"
_KEY_FILE = DATA_DIR / "secret.key"

_fernet: Fernet | None = None


def _load_key() -> bytes:
    env = os.environ.get("RB_SECRET_KEY", "").strip()
    if env:
        try:
            raw = base64.urlsafe_b64decode(env.encode())
            if len(raw) == 32:
                return env.encode()
        except Exception:
            pass
        return base64.urlsafe_b64encode(hashlib.sha256(env.encode()).digest())

    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes().strip()

    key = Fernet.generate_key()
    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _KEY_FILE.write_bytes(key)
    os.chmod(_KEY_FILE, 0o600)
    return key


def _cipher() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_key())
    return _fernet


def is_encrypted(value: str) -> bool:
    return bool(value) and value.startswith(PREFIX)


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    token = _cipher().encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{PREFIX}{token}"


def decrypt(stored: str) -> str:
    """兼容历史明文；密文无法解密（换过主密钥）时返回空串。"""
    if not stored:
        return ""
    if not is_encrypted(stored):
        return stored
    try:
        return _cipher().decrypt(stored[len(PREFIX) :].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""
