"""文本归一化工具：标签去重、模糊匹配共用。"""

from __future__ import annotations

import re
import unicodedata


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKC", (name or "").strip().lower())
    text = re.sub(r"\s+", "", text)
    return text
