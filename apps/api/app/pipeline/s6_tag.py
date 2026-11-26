"""s6 打标（文档级，幂等）：本地词表匹配 + LLM 语义打标（知识点）。

两条路径叠加，结果按 tag 去重、取较高置信度：

1. 本地词表（始终执行）：题干/解答里直接出现的 approved 标签名、canned 识别结果、
   题干抽出的中文短语，经模糊对齐后挂 `weight=0.6`；匹配不上的短语只建
   `Tag(type="knowledge", status="pending")`，绝不直接 approved，也不绑定题目。
2. LLM（仅在设置页配置了可用 Key 时执行）：先用字符 bigram 召回 40 个候选知识点，
   再由模型从候选中选择并给置信度；命中 approved 标签才挂 `weight=置信度`，
   模型编造的名字只计数、不建标签，避免词表被自由生成的同义词污染。

方法论标签暂不在这里生成：它依赖参考答案/订正的解题步骤，属于后续单独阶段。
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import NamedTuple

from sqlalchemy.orm import Session

from ..models import Page, Problem, ProblemTag, Region, Solution, Tag
from ..textutil import normalize_name
from .base import StageContext, StageResult
from .providers.mock import load_canned
from .providers.register import get_chat_provider

RATIO_MIN = 0.6
MAX_TAGS_PER_PROBLEM = 8
CHINESE_RUN = re.compile(r"[\u4e00-\u9fff]{2,8}")

HEURISTIC_WEIGHT = 0.6
LLM_BATCH = 8
LLM_CANDIDATES = 40
LLM_MAX_TAGS = 5
LLM_MIN_CONFIDENCE = 0.55
LLM_SOURCE = "ai:knowledge-v1"

SYSTEM_PROMPT = (
    "你是中小学教研员，负责给题目标注知识点。只能从给定的候选知识点里选择，"
    "不得编造新名称；候选不合适就返回空数组，宁可少选也不要凑数。"
    "只输出 JSON，不要 markdown 代码围栏，不要解释。"
)


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


def _bigrams(text: str) -> set[str]:
    clean = normalize_name(text or "")
    if len(clean) < 2:
        return {clean} if clean else set()
    return {clean[i : i + 2] for i in range(len(clean) - 1)}


def _tag_text(tag: Tag) -> str:
    parts = [tag.name, tag.chapter or "", (tag.description or "")[:80]]
    return " ".join(part for part in parts if part)


def _recall(problem: Problem, pool: list[Tag], grams: dict[str, set[str]]) -> list[Tag]:
    """按字符 bigram 重合度 + 名称命中 + 同学科加成，召回候选知识点。"""
    stem = problem.stem_text or problem.stem_latex or ""
    stem_key = normalize_name(stem)
    stem_grams = _bigrams(stem)
    scored: list[tuple[float, Tag]] = []
    for tag in pool:
        tag_grams = grams.get(tag.id) or set()
        score = len(stem_grams & tag_grams) / ((len(tag_grams) ** 0.5) + 1.0)
        if tag.normalized_name and tag.normalized_name in stem_key:
            score += 0.8
        if tag.subject and tag.subject == problem.subject:
            score += 0.1
        if score > 0:
            scored.append((score, tag))
    scored.sort(key=lambda item: (-item[0], item[1].name))
    return [tag for _, tag in scored[:LLM_CANDIDATES]]


def _clamp(value: object) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _user_prompt(items: list[dict]) -> str:
    return (
        "为每道题从 candidates 中选出 1–4 个最贴合的知识点，confidence 取 0–1。\n"
        "只输出 JSON："
        '{"items":[{"id":0,"knowledge":[{"name":"候选里的原名","confidence":0.0}]}]}\n'
        "题目数据：\n" + json.dumps(items, ensure_ascii=False)
    )


class _Plan(NamedTuple):
    problem: Problem
    picks: dict[str, float]  # tag_id -> weight
    phrases: list[str]


class TagStage:
    name = "tag"

    def __init__(self, chat=None) -> None:
        # chat 仅用于测试注入；生产环境按 AI 配置动态创建
        self._chat = chat

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

        plans = [self._heuristic_plan(session, problem, approved, canned) for problem in problems]

        warnings: list[str] = []
        llm_stats = {"llm_problems": 0, "llm_tags": 0, "llm_unresolved": 0}
        chat = self._chat if self._chat is not None else get_chat_provider(session)
        if chat is not None and plans:
            try:
                llm_stats = self._apply_llm(plans, approved, chat)
            except Exception as exc:  # 模型故障不阻断批量导入
                warnings.append(f"LLM 打标失败，已回退本地词表：{exc}")

        attached = pending_created = 0
        for plan in plans:
            problem = plan.problem
            session.query(ProblemTag).filter(ProblemTag.problem_id == problem.id).delete(
                synchronize_session=False
            )
            for tag_id, weight in plan.picks.items():
                session.merge(
                    ProblemTag(
                        problem_id=problem.id, tag_id=tag_id, weight=weight, source="ai"
                    )
                )
                attached += 1

            for phrase in plan.phrases:
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
        return StageResult(
            ok=True,
            warnings=warnings,
            stats={
                "problems": len(problems),
                "tags": attached,
                "pending_created": pending_created,
                **llm_stats,
            },
        )

    def _heuristic_plan(
        self, session: Session, problem: Problem, approved: list[Tag], canned: list
    ) -> _Plan:
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

        pressed: dict[str, float] = {}
        for name, tag_type in candidates[:MAX_TAGS_PER_PROBLEM]:
            tag = self._resolve(name, tag_type, approved)
            if tag is None:
                continue
            pressed[tag.id] = max(pressed.get(tag.id, 0.0), HEURISTIC_WEIGHT)
        return _Plan(problem=problem, picks=pressed, phrases=phrases)

    @staticmethod
    def _apply_llm(plans: list[_Plan], approved: list[Tag], chat) -> dict[str, int]:
        pool = [tag for tag in approved if tag.type == "knowledge"]
        grams = {tag.id: _bigrams(_tag_text(tag)) for tag in pool}
        stats = {"llm_problems": 0, "llm_tags": 0, "llm_unresolved": 0}

        for start in range(0, len(plans), LLM_BATCH):
            batch = plans[start : start + LLM_BATCH]
            items: list[dict] = []
            for offset, plan in enumerate(batch):
                problem = plan.problem
                recalled = _recall(problem, pool, grams)
                if not recalled:
                    continue
                items.append(
                    {
                        "id": offset,
                        "subject": problem.subject,
                        "stem": (problem.stem_text or problem.stem_latex or "")[:600],
                        "candidates": [tag.name for tag in recalled],
                    }
                )
            if not items:
                continue

            data = chat.complete_json(SYSTEM_PROMPT, _user_prompt(items))
            rows: dict[int, list] = {}
            for row in data.get("items") or []:
                if not isinstance(row, dict):
                    continue
                try:
                    rows[int(row.get("id", -1))] = row.get("knowledge") or []
                except (TypeError, ValueError):
                    continue

            for offset, plan in enumerate(batch):
                stats["llm_problems"] += 1
                for pick in (rows.get(offset) or [])[:LLM_MAX_TAGS]:
                    if not isinstance(pick, dict):
                        continue
                    confidence = _clamp(pick.get("confidence"))
                    if confidence < LLM_MIN_CONFIDENCE:
                        continue
                    tag = TagStage._resolve(str(pick.get("name") or ""), "knowledge", pool)
                    if tag is None:
                        stats["llm_unresolved"] += 1
                        continue
                    plan.picks[tag.id] = max(plan.picks.get(tag.id, 0.0), confidence)
                    stats["llm_tags"] += 1

        # 单题标签上限：按置信度排序后裁剪
        for plan in plans:
            if len(plan.picks) <= MAX_TAGS_PER_PROBLEM:
                continue
            ordered = sorted(plan.picks.items(), key=lambda item: -item[1])
            plan.picks.clear()
            plan.picks.update(ordered[:MAX_TAGS_PER_PROBLEM])
        return stats

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
            if not candidate:
                continue
            if key in candidate or candidate in key:
                return tag
            if abs(len(key) - len(candidate)) <= 4 and _ratio(key, candidate) >= RATIO_MIN:
                return tag
        return None

    @classmethod
    def _resolve(cls, name: str, tag_type: str, approved: list[Tag]) -> Tag | None:
        pool = [tag for tag in approved if tag.type == tag_type]
        return cls._fuzzy_tag(name, pool)


STAGE = TagStage()
