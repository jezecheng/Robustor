"""s4 识别：把每个块变成 LaTeX/文本 + 置信度，并把批改块映射成 mark 行。

- stem / answer / correction：layout 已带 text 时保留（只校验/回填 confidence），
  否则裁剪该 region 调 OcrProvider。
- mark：写一条 mark（problem_id 可空，由 s5 装配时回填），覆盖常见判分符号。
- 幂等：开跑先删本页旧 mark；crop 一律落盘，文件名以 region id 为前缀便于排查。
"""

from __future__ import annotations

import math
import re

from ..models import Mark, Page, Region
from .base import StageContext, StageResult, fail_result, ok_result
from .providers.base import OcrProvider
from .providers.register import get_ocr_provider

RECOGNIZABLE = ("stem", "answer", "correction")

# 判分符号 → verdict。按"符号 → 分数提示 → 分数形式"的顺序匹配，未命中即 unknown。
TICK_TOKENS = ("✓", "√", "V")
CROSS_TOKENS = ("✗", "×", "x", "X")
PARTIAL_TOKENS = ("△", "半")
SCORE_HINTS = ("+", "-")
# 形如 5/10、3.5/5、1/2 分 的分数式判分
FRACTION_RE = re.compile(r"^\s*[+-]?\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?\s*分?\s*$")


def symbol_to_verdict(symbol: str) -> str:
    text = (symbol or "").strip()
    if not text:
        return "unknown"
    if any(token in text for token in TICK_TOKENS):
        return "right"
    if any(token in text for token in CROSS_TOKENS):
        return "wrong"
    if any(token in text for token in PARTIAL_TOKENS):
        return "partial"
    if any(token in text for token in SCORE_HINTS):
        return "partial"
    if FRACTION_RE.match(text):
        return "partial"
    return "unknown"


def _valid_confidence(value: object) -> float | None:
    """置信度必须是 [0, 1] 内的有限数，否则返回 None 交给调用方回填。"""
    try:
        conf = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(conf) or not 0.0 <= conf <= 1.0:
        return None
    return round(conf, 3)


class RecognizeStage:
    name = "recognize"

    def run(self, ctx: StageContext) -> StageResult:
        page = ctx.session.get(Page, ctx.page_id)
        if page is None:
            return fail_result("page not found")

        regions = ctx.session.query(Region).filter(Region.page_id == page.id).all()
        region_ids = [r.id for r in regions]
        if region_ids:
            # 幂等：先删本页旧的 mark，再按当前 region 重建
            ctx.session.query(Mark).filter(Mark.region_id.in_(region_ids)).delete(
                synchronize_session=False
            )

        provider = get_ocr_provider(ctx.session)
        warnings: list[str] = []
        recognized = 0
        marks = 0

        for region in regions:
            if region.block_type in RECOGNIZABLE:
                if (region.text or "").strip():
                    # layout 已带入文本：保留文本，只校验/回填 confidence
                    conf = _valid_confidence(region.confidence)
                    if conf is None:
                        _, conf = self._recognize_crop(ctx, page, region, provider, warnings)
                    region.confidence = conf
                    recognized += 1
                else:
                    text, conf = self._recognize_crop(ctx, page, region, provider, warnings)
                    if text.strip():
                        region.text = text
                        region.confidence = conf
                        recognized += 1
                    else:
                        warnings.append(f"region {region.id}: empty OCR result")
            elif region.block_type == "mark":
                symbol = (region.text or "").strip()
                if not symbol:
                    symbol, conf = self._recognize_crop(ctx, page, region, provider, warnings)
                    if symbol:
                        region.text = symbol
                        region.confidence = conf
                symbol = symbol or "unknown"
                ctx.session.add(
                    Mark(
                        region_id=region.id,
                        raw_symbol=symbol[:32],
                        verdict=symbol_to_verdict(symbol),
                        problem_id=None,
                    )
                )
                marks += 1

        ctx.session.commit()
        return ok_result(
            regions=len(regions),
            recognized=recognized,
            marks=marks,
            provider=provider.name,
        )

    def _recognize_crop(
        self,
        ctx: StageContext,
        page: Page,
        region: Region,
        provider: OcrProvider,
        warnings: list[str],
    ) -> tuple[str, float]:
        bbox = [float(v) for v in (region.bbox or [])]
        if len(bbox) != 4:
            warnings.append(f"region {region.id}: invalid bbox, skip OCR")
            return "", 0.0
        # crop 落盘（storage.crop），文件名以 region id 前缀，便于排查
        crop_rel = ctx.storage.crop(page.image_path, bbox, f"{region.id[:8]}_ocr")
        latex, conf = provider.recognize(ctx.storage.read(crop_rel), region.block_type)
        return str(latex), _valid_confidence(conf) or 0.0


STAGE = RecognizeStage()
