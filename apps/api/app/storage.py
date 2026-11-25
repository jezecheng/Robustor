"""本地文件读写：图片落盘、缩放、裁剪。所有路径相对 data/ 存储，前端经 /media 访问。"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from .config import DATA_DIR, MAX_EDGE


def _downscale(img: Image.Image, max_edge: int = MAX_EDGE) -> Image.Image:
    longest = max(img.width, img.height)
    if longest <= max_edge:
        return img
    ratio = max_edge / float(longest)
    return img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)


class Storage:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = Path(data_dir or DATA_DIR)

    def abs(self, rel: str) -> Path:
        return self.data_dir / rel

    def read(self, rel: str) -> bytes:
        return self.abs(rel).read_bytes()

    def save_page(self, document_id: str, idx: int, data: bytes) -> tuple[str, int, int]:
        """保存一页原图（长边 ≤ MAX_EDGE），返回 (相对路径, 宽, 高)。"""
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img = _downscale(img)
        rel = f"media/pages/{document_id}/p{idx}.jpg"
        path = self.abs(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path, format="JPEG", quality=88)
        return rel, img.width, img.height

    def crop(
        self,
        rel: str,
        bbox: list[float],
        name: str,
        pad: float = 0.004,
    ) -> str:
        """按归一化 bbox 裁剪，返回相对路径。"""
        img = Image.open(self.abs(rel)).convert("RGB")
        w, h = img.size
        x, y, bw, bh = bbox
        left = max(0, int((x - pad) * w))
        top = max(0, int((y - pad) * h))
        right = min(w, int((x + bw + pad) * w))
        bottom = min(h, int((y + bh + pad) * h))
        if right <= left or bottom <= top:
            right, bottom = min(w, left + 2), min(h, top + 2)
        out_rel = f"media/crops/{name}.jpg"
        out = self.abs(out_rel)
        out.parent.mkdir(parents=True, exist_ok=True)
        img.crop((left, top, right, bottom)).save(out, format="JPEG", quality=90)
        return out_rel
