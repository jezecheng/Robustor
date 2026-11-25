"""s6 打标（文档级，幂等）：种子标签模糊匹配 → 关联 approved；未命中新词落 pending。

候选标签词来源（mock 模式无名模型，canned 只当"候选词"用，最终必须落到种子词表）：
1. 题干文本里直接出现的种子标签名；
2. canned 识别结果里的 knowledge / method（按 region 引用或题干包含关系定位）；
3. 题干中抽出的中文短语（模糊匹配种子标签）。

候选词一律经 `_resolve` 模糊对齐到 **approved** 种子标签（规范化等值 / 双向包含 /
SequenceMatcher ratio ≥ 0.6）后写 `problem_tag(source="ai", weight=1.0)`；
匹配不上的中文短语只建 `Tag(type="knowledge", status="pending")`，按 normalized_name 去重，
绝不直接 approved，也不绑定到 problem。
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from ..models import Page, Problem, ProblemTag, Region, Solution, Tag
from ..textutil import normalize_name
from .base import StageContext, StageResult, ok_result
from .providers.mock import load_canned

RATIO_MIN = 0.6
MAX_TAGS_PER_PROBLEM = 8
CHINESE_RUN = re.compile(r"[\u4e00-\u9fff]{2,8}")


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _extract_phrases(text: str) -> list[str]:
    """抽中文短语（2–8 字连续中文）；按首次出现顺序去重。"""
    seen: set[str] = set()
    phrases: list[str] = []
    for match in CHINESE_RUN.finditer(text or ""):
        phrase = match.group(0)
        key = normalize_name(phrase)
        if key and key not in seen:
            seen.add(key)
            phrases.append(phrase)
    return phrases


class TagStage:
    name = "tag"

    def run(self, ctx: StageContext) -> StageResult:
        session = ctx.session
        problems = (
            session.query(Problem)
            .filter(Problem.document_id == ctx.document_id, Problem.status == "draft")
            .all()
        )
        approved = session.query(Tag).filter(Tag.status == "approved").all()
        known = {(tag.type, tag.normalized_name): tag for tag in session.query(Tag).all()}
        canned = load_canned().get("problems", [])

        attached = 0
        pending_created = 0
        for problem in problems:
            session.query(ProblemTag).filter(ProblemTag.problem_id == problem.id).delete(
                synchronize_session=False
            )
            haystack = self._haystack(session, problem)
            candidates: list[tuple[str, str]] = []
            seen: set[tuple[str, str]] = set()

            def push(name: str, tag_type: str) -> None:
                key = (tag_type, normalize_name(name))
                if key[1] and key not in seen:
                    seen.add(key)
                    candidates.append((name, tag_type))

            for tag in approved:
                if tag.name and tag.name in haystack:
                    push(tag.name, tag.type)

            spec = self._canned_spec(session, problem, canned)
            if spec:
                for name in spec.get("knowledge", []):
                    push(str(name), "knowledge")
                for name in spec.get("method", []):
                    push(str(name), "method")

            phrases = _extract_phrases(problem.stem_text or problem.stem_latex)
            for phrase in phrases:
                tag = self._fuzzy_tag(phrase, approved)
                if tag is not None:
                    push(tag.name, tag.type)

            used: set[str] = set()
            for name, tag_type in candidates[:MAX_TAGS_PER_PROBLEM]:
                tag = self._resolve(name, tag_type, approved)
                if tag is None or tag.id in used:
                    continue
                used.add(tag.id)
                session.merge(
                    ProblemTag(problem_id=problem.id, tag_id=tag.id, weight=1.0, source="ai")
                )
                attached += 1

            for phrase in phrases:
                if self._fuzzy_tag(phrase, approved) is not None:
                    continue
                key = ("knowledge", normalize_name(phrase))
                if key in known:
                    continue
                tag = Tag(type="knowledge", name=phrase, normalized_name=key[1], status="pending")
                session.add(tag)
                session.flush()
                known[key] = tag
                pending_created += 1

        session.commit()
        return ok_result(
            problems=len(problems), tags=attached, pending_created=pending_created
        )

    @staticmethod
    def _haystack(session: Session, problem: Problem) -> str:
        solutions = session.query(Solution).filter(Solution.problem_id == problem.id).all()
        parts = [problem.stem_latex or "", problem.stem_text or ""]
        parts.extend(solution.latex or "" for solution in solutions)
        return "\n".join(part for part in parts if part)

    @staticmethod
    def _canned_spec(session: Session, problem: Problem, canned: list) -> dict | None:
        if not canned:
            return None
        rows = (
            session.query(Page.idx, Region.order_idx)
            .join(Region, Region.page_id == Page.id)
            .filter(Region.problem_id == problem.id, Region.block_type == "stem")
            .all()
        )
        refs = {(int(idx), int(order)) for idx, order in rows}
        best: dict | None = None
        best_overlap = 0
        for spec in canned:
            spec_refs = {(int(a), int(b)) for a, b in spec.get("refs", [])}
            overlap = len(spec_refs & refs)
            if overlap > best_overlap:
                best, best_overlap = spec, overlap
        if best is not None:
            return best

        stem = normalize_name(problem.stem_latex or "")
        for spec in canned:
            key = normalize_name(spec.get("stem_latex", ""))
            if key and (key in stem or _ratio(key, stem) >= RATIO_MIN):
                return spec
        return None

    @staticmethod
    def _fuzzy_tag(name: str, approved: list[Tag]) -> Tag | None:
        key = normalize_name(name)
        if not key:
            return None
        for tag in approved:
            if tag.normalized_name == key:
                return tag
        for tag in approved:
            candidate = tag.normalized_name
            if candidate and (key in candidate or candidate in key or _ratio(key, candidate) >= RATIO_MIN):
                return tag
        return None

    @classmethod
    def _resolve(cls, name: str, tag_type: str, approved: list[Tag]) -> Tag | None:
        pool = [tag for tag in approved if tag.type == tag_type]
        return cls._fuzzy_tag(name, pool)


STAGE = TagStage()
