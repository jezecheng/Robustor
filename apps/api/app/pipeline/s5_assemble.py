"""s5 装配（文档级，幂等）：阅读顺序归组 → 跨页续写判定 → 图文绑定 → mark 回填。

规则（只用 region 文本判定，不依赖 canned 的 problems 归组）：
1. 按 (page.idx, order_idx) 排成阅读顺序，每个 stem 起一道题；
2. 题干未以句末标点结尾且下一个 stem 不是新的编号条目，或题干出现
   `(cont.)` / `（续）` / `如图` / `Figure` 时，与下一个 stem 合并（跨页时把
   首个 stem 的 page_end 推到后者所在页）；
3. stem 之后、下一个 stem 之前的 answer / correction / mark 归入该题；
4. figure 绑到最近的、题干含"图"或同页的题目，crop 落盘写 problem_image；
5. 每题 `Problem(status="draft")`；answer→student、correction→correction 的 Solution；mark 回填 problem_id / solution_id。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models import Document, Mark, Page, Problem, ProblemImage, ProblemTag, Region, Solution
from .base import StageContext, StageResult, ok_result

TERMINAL = (".", "。", "?", "!", "？", "！")
CONTINUE_MARKERS = ("(cont.)", "（cont.）", "（续）", "(续)", "如图", "figure", "fig.")
ITEM_RE = re.compile(r"^\s*(?:第\s*)?[（(]?\d{1,3}\s*[.、．)）]")
VISUAL_RE = re.compile(r"图|figure|fig\.", re.IGNORECASE)


def _delete_draft_problems(session: Session, document_id: str) -> None:
    ids = [
        row[0]
        for row in session.query(Problem.id)
        .filter(Problem.document_id == document_id, Problem.status == "draft")
        .all()
    ]
    if not ids:
        return
    solution_ids = [
        row[0] for row in session.query(Solution.id).filter(Solution.problem_id.in_(ids)).all()
    ]
    session.query(Solution).filter(Solution.problem_id.in_(ids)).delete(synchronize_session=False)
    session.query(ProblemImage).filter(ProblemImage.problem_id.in_(ids)).delete(
        synchronize_session=False
    )
    session.query(ProblemTag).filter(ProblemTag.problem_id.in_(ids)).delete(
        synchronize_session=False
    )
    session.query(Mark).filter(Mark.problem_id.in_(ids)).update(
        {Mark.problem_id: None}, synchronize_session=False
    )
    if solution_ids:
        session.query(Mark).filter(Mark.solution_id.in_(solution_ids)).update(
            {Mark.solution_id: None}, synchronize_session=False
        )
    session.query(Region).filter(Region.problem_id.in_(ids)).update(
        {Region.problem_id: None}, synchronize_session=False
    )
    session.query(Problem).filter(Problem.id.in_(ids)).delete(synchronize_session=False)
    session.flush()


def _starts_new_item(text: str) -> bool:
    return bool(ITEM_RE.match(text or ""))


def _needs_merge(stem_text: str, next_stem_text: str) -> bool:
    """题干是否未闭合、需要与下一个 stem 合并。"""
    text = (stem_text or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if any(marker in lowered for marker in CONTINUE_MARKERS):
        return True
    if text.endswith(TERMINAL):
        return False
    return not _starts_new_item(next_stem_text)


@dataclass
class _Group:
    stems: list[Region] = field(default_factory=list)
    extras: list[Region] = field(default_factory=list)
    first_pos: int = 0
    page_idxs: set[int] = field(default_factory=set)


class AssembleStage:
    name = "assemble"

    def run(self, ctx: StageContext) -> StageResult:
        session = ctx.session
        document = session.get(Document, ctx.document_id)
        if document is None:
            return StageResult(ok=False, warnings=["document not found"], stats={})

        _delete_draft_problems(session, document.id)

        rows = (
            session.query(Region, Page.idx)
            .join(Page, Page.id == Region.page_id)
            .filter(Region.document_id == document.id)
            .order_by(Page.idx, Region.order_idx, Region.id)
            .all()
        )
        ordered = [(region, idx) for region, idx in rows if region.block_type != "noise"]
        page_idx_of = {region.id: idx for region, idx in ordered}

        groups = self._group(ordered)
        infos: list[tuple[Problem, _Group]] = []
        merged_cross_page = 0
        for group in groups:
            problem, first_page, last_page = self._create_problem(session, document, group, page_idx_of)
            if last_page > first_page:
                merged_cross_page += 1
            infos.append((problem, group))

        figures_bound = self._bind_figures(ctx, ordered, infos)

        session.commit()
        return ok_result(
            problems=len(infos),
            merged_cross_page=merged_cross_page,
            figures_bound=figures_bound,
            regions=len(ordered),
        )

    @staticmethod
    def _group(ordered: list[tuple[Region, int]]) -> list[_Group]:
        groups: list[_Group] = []
        current: _Group | None = None
        for pos, (region, page_idx) in enumerate(ordered):
            if region.block_type == "stem":
                if (
                    current is not None
                    and current.stems
                    and _needs_merge(current.stems[-1].text, region.text)
                ):
                    current.stems.append(region)
                    current.page_idxs.add(page_idx)
                    continue
                current = _Group(stems=[region], first_pos=pos, page_idxs={page_idx})
                groups.append(current)
            elif current is not None:
                current.extras.append(region)
                current.page_idxs.add(page_idx)
        return groups

    @staticmethod
    def _create_problem(
        session: Session, document: Document, group: _Group, page_idx_of: dict[str, int]
    ) -> tuple[Problem, int, int]:
        stem_latex = "\n".join(
            (region.text or "").strip() for region in group.stems if (region.text or "").strip()
        )
        problem = Problem(
            document_id=document.id,
            subject=document.subject,
            stem_latex=stem_latex,
            stem_text=stem_latex,
            status="draft",
        )
        session.add(problem)
        session.flush()

        members = group.stems + group.extras
        for region in members:
            region.problem_id = problem.id

        first_page = page_idx_of[group.stems[0].id]
        last_page = page_idx_of[group.stems[-1].id]
        if last_page > first_page:
            group.stems[0].page_end = max(group.stems[0].page_end, last_page)

        student_solution: Solution | None = None
        for region in group.extras:
            if region.block_type == "answer":
                solution = Solution(
                    problem_id=problem.id,
                    kind="student",
                    latex=region.text or "",
                    ink_role="answer",
                    confidence=region.confidence,
                )
                session.add(solution)
                session.flush()
                if student_solution is None:
                    student_solution = solution
            elif region.block_type == "correction":
                session.add(
                    Solution(
                        problem_id=problem.id,
                        kind="correction",
                        latex=region.text or "",
                        ink_role="correction",
                        confidence=region.confidence,
                    )
                )
        session.flush()

        mark_region_ids = [region.id for region in members if region.block_type == "mark"]
        for mark in session.query(Mark).filter(Mark.region_id.in_(mark_region_ids)).all():
            mark.problem_id = problem.id
            if student_solution is not None:
                mark.solution_id = student_solution.id
        return problem, first_page, last_page

    @staticmethod
    def _bind_figures(
        ctx: StageContext, ordered: list[tuple[Region, int]], infos: list[tuple[Problem, _Group]]
    ) -> int:
        session = ctx.session
        bound = 0
        for pos, (region, page_idx) in enumerate(ordered):
            if region.block_type != "figure":
                continue
            preceding = [(problem, group) for problem, group in infos if group.first_pos < pos]
            target: Problem | None = None
            for problem, _group in reversed(preceding):
                if VISUAL_RE.search(problem.stem_text or ""):
                    target = problem
                    break
            if target is None:
                for problem, group in reversed(preceding):
                    if page_idx in group.page_idxs:
                        target = problem
                        break
            if target is None and preceding:
                target = preceding[-1][0]
            page = session.get(Page, region.page_id)
            if target is None or page is None:
                continue

            index = session.query(ProblemImage).filter(
                ProblemImage.problem_id == target.id
            ).count() + 1
            image_path = ctx.storage.crop(page.image_path, region.bbox, f"{target.id[:8]}_fig{index}")
            region.problem_id = target.id
            session.add(
                ProblemImage(
                    problem_id=target.id,
                    region_id=region.id,
                    image_path=image_path,
                    caption=f"图 {index}",
                )
            )
            bound += 1
        return bound


STAGE = AssembleStage()
