"""Mock provider：读 fixtures/canned.json，保证全链路在无模型时也能跑通。"""

from __future__ import annotations

import json
from functools import lru_cache

from ...config import CANNED_PATH

DEFAULT_OCR: dict[str, tuple[str, float]] = {
    "stem": ("x^2-5x+6=0", 0.90),
    "answer": ("x=2 \\text{ or } x=3", 0.85),
    "correction": ("x^2-5x+6=(x-2)(x-3)", 0.82),
    "mark": ("✗", 0.91),
}


@lru_cache(maxsize=1)
def load_canned() -> dict:
    if not CANNED_PATH.exists():
        return {"pages": [], "problems": [], "ocr": {}}
    return json.loads(CANNED_PATH.read_text(encoding="utf-8"))


def clear_cache() -> None:
    load_canned.cache_clear()


class MockLayoutProvider:
    name = "mock"

    def detect(self, image_bytes: bytes, page_idx: int, cfg: dict) -> list[dict]:
        pages = load_canned().get("pages", [])
        if not pages:
            return []
        page = pages[(page_idx - 1) % len(pages)]
        out: list[dict] = []
        for i, region in enumerate(page.get("regions", [])):
            item = dict(region)
            item.setdefault("order_idx", i)
            item.setdefault("page_start", page_idx)
            item.setdefault("page_end", page_idx)
            item.setdefault("confidence", 0.8)
            item.setdefault("text", "")
            out.append(item)
        return out


class MockOcrProvider:
    name = "mock"

    def recognize(self, image_bytes: bytes, hint: str) -> tuple[str, float]:
        canned = load_canned().get("ocr", {})
        if hint in canned:
            value = canned[hint]
            return str(value[0]), float(value[1])
        return DEFAULT_OCR.get(hint, ("", 0.5))
