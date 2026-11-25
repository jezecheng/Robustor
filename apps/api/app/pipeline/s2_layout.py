"""s2 版面切块（WP0 stub：走 LayoutProvider，mock 下读 canned 坐标）。

WP2 在此补：投影法切行、连通域合并、规则后处理、OpenCV provider。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Mark, Page, Region
from .base import StageContext, StageResult, ok_result
from .providers.register import get_layout_provider


def _clear_page_regions(session: Session, page_id: str) -> None:
    old_ids = [row[0] for row in session.query(Region.id).filter(Region.page_id == page_id).all()]
    if old_ids:
        session.query(Mark).filter(Mark.region_id.in_(old_ids)).delete(synchronize_session=False)
        session.query(Region).filter(Region.id.in_(old_ids)).delete(synchronize_session=False)
    session.flush()


class LayoutStage:
    name = "layout"

    def run(self, ctx: StageContext) -> StageResult:
        page = ctx.session.get(Page, ctx.page_id)
        if page is None:
            return StageResult(ok=False, warnings=["page not found"], stats={})

        provider = get_layout_provider()
        candidates = provider.detect(ctx.storage.read(page.image_path), page.idx, ctx.config)

        _clear_page_regions(ctx.session, page.id)

        for i, cand in enumerate(candidates):
            bbox = [float(v) for v in cand.get("bbox", [0, 0, 0, 0])]
            ctx.session.add(
                Region(
                    page_id=page.id,
                    document_id=ctx.document_id,
                    block_type=cand.get("block_type", "stem"),
                    ink_role=cand.get("ink_role"),
                    bbox=bbox,
                    page_start=int(cand.get("page_start", page.idx)),
                    page_end=int(cand.get("page_end", page.idx)),
                    confidence=float(cand.get("confidence", 0.0)),
                    order_idx=int(cand.get("order_idx", i)),
                    text=str(cand.get("text", "")),
                )
            )
        ctx.session.commit()
        types: dict[str, int] = {}
        for cand in candidates:
            key = str(cand.get("block_type", "stem"))
            types[key] = types.get(key, 0) + 1
        return ok_result(
            regions=len(candidates), provider=provider.name, page_idx=page.idx, block_types=types
        )


STAGE = LayoutStage()
