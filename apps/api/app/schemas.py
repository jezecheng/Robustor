"""Pydantic v2 请求/响应模型 —— OpenAPI 单一来源。WP0 拥有，其他 WP 只读。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

BlockType = Literal["stem", "figure", "answer", "mark", "correction", "noise"]
InkRole = Literal["print", "answer", "mark", "correction", "ignore"]
SolutionKind = Literal["student", "correction", "reference", "ai"]
Verdict = Literal["right", "wrong", "partial", "unknown"]
TagType = Literal["knowledge", "method"]
TagStatus = Literal["approved", "pending"]
ProblemStatus = Literal["draft", "confirmed"]
JobStage = Literal["preprocess", "layout", "ink", "recognize", "assemble", "tag"]
JobStatus = Literal["queued", "running", "done", "failed"]
PageStatus = Literal["pending", "ready", "failed"]
BBox = list[float]  # [x, y, w, h] 归一化 0–1，原图未旋转坐标系
AiProvider = Literal["mock", "vlm"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- 文档 / 页面 / 任务


class PageOut(ORMModel):
    id: str
    document_id: str
    idx: int
    image_path: str
    width: int
    height: int
    rotation: float
    status: PageStatus
    region_count: int = 0


class JobOut(BaseModel):
    id: str
    document_id: str
    stage: JobStage
    status: JobStatus
    progress: float
    detail: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentOut(ORMModel):
    id: str
    subject: str
    source_name: str
    page_count: int
    created_at: datetime
    pages: list[PageOut] = Field(default_factory=list)
    job: JobOut | None = None


class DocumentListItem(ORMModel):
    id: str
    subject: str
    source_name: str
    page_count: int
    created_at: datetime
    problem_count: int = 0


class DocumentCreated(BaseModel):
    document_id: str
    job_id: str


# ---------------------------------------------------------------- 区域


class RegionOut(ORMModel):
    id: str
    page_id: str
    document_id: str
    problem_id: str | None = None
    block_type: BlockType
    ink_role: InkRole | None = None
    bbox: BBox
    page_start: int
    page_end: int
    confidence: float
    order_idx: int
    text: str = ""


class RegionPatch(BaseModel):
    bbox: BBox | None = None
    block_type: BlockType | None = None
    page_start: int | None = None
    page_end: int | None = None


class RegionMergeIn(BaseModel):
    region_ids: list[str] = Field(min_length=2)


# ---------------------------------------------------------------- 题目


class SolutionIn(BaseModel):
    kind: SolutionKind = "student"
    latex: str = ""
    ink_role: InkRole = "answer"
    confidence: float = 0.0


class SolutionOut(SolutionIn):
    id: str
    problem_id: str


class MarkIn(BaseModel):
    verdict: Verdict = "unknown"
    raw_symbol: str = ""
    score: float | None = None
    solution_id: str | None = None


class MarkOut(MarkIn):
    id: str
    problem_id: str | None = None
    region_id: str | None = None


class ProblemImageOut(ORMModel):
    id: str
    problem_id: str
    region_id: str | None = None
    image_path: str
    caption: str = ""


class ProblemTagOut(BaseModel):
    id: str
    type: TagType
    name: str
    source: str = "ai"
    weight: float = 1.0


class ProblemCreate(BaseModel):
    document_id: str
    region_ids: list[str] = Field(default_factory=list)
    stem_latex: str = ""
    subject: str = "math"
    solutions: list[SolutionIn] = Field(default_factory=list)
    marks: list[MarkIn] = Field(default_factory=list)


class ProblemPatch(BaseModel):
    stem_latex: str | None = None
    subject: str | None = None
    status: ProblemStatus | None = None


class ProblemOut(ORMModel):
    id: str
    document_id: str
    subject: str
    stem_latex: str
    stem_text: str
    status: ProblemStatus
    created_at: datetime
    images: list[ProblemImageOut] = Field(default_factory=list)
    solutions: list[SolutionOut] = Field(default_factory=list)
    marks: list[MarkOut] = Field(default_factory=list)
    tags: list[ProblemTagOut] = Field(default_factory=list)


class ProblemListOut(BaseModel):
    items: list[ProblemOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    size: int = 20


class ProblemTagsIn(BaseModel):
    knowledge: list[str] = Field(default_factory=list)  # tag_id
    method: list[str] = Field(default_factory=list)  # tag_id


class SolutionsReplaceIn(BaseModel):
    solutions: list[SolutionIn] = Field(default_factory=list)


# ---------------------------------------------------------------- 标签


class TagOut(ORMModel):
    id: str
    type: TagType
    name: str
    normalized_name: str
    parent_id: str | None = None
    status: TagStatus


class TagIn(BaseModel):
    type: TagType = "knowledge"
    name: str
    parent_id: str | None = None


class TagMergeIn(BaseModel):
    from_id: str
    to_id: str


# ---------------------------------------------------------------- 统计 / 复习


class StatItem(BaseModel):
    name: str
    count: int


class StatsOverview(BaseModel):
    total: int = 0
    by_subject: list[StatItem] = Field(default_factory=list)
    by_knowledge: list[StatItem] = Field(default_factory=list)
    by_method: list[StatItem] = Field(default_factory=list)
    due_today: int = 0


class ReviewIn(BaseModel):
    grade: int = Field(ge=0, le=3)


class ReviewOut(BaseModel):
    problem_id: str
    ease: float
    interval_days: int
    due_at: datetime


# ---------------------------------------------------------------- 墨迹方案


class InkProfileIn(BaseModel):
    name: str = "新方案"
    is_default: bool = False
    rules_json: dict[str, Any] = Field(default_factory=dict)


class InkProfilePatch(BaseModel):
    name: str | None = None
    is_default: bool | None = None
    rules_json: dict[str, Any] | None = None


class InkProfileOut(ORMModel):
    id: str
    name: str
    is_default: bool
    rules_json: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------- AI API 配置


class AiProviderIn(BaseModel):
    name: str = ""
    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_key: str = Field(min_length=1)


class AiProviderPatch(BaseModel):
    name: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None  # 不传或留空表示保持原 Key
    is_active: bool | None = None


class AiProviderOut(BaseModel):
    id: str
    name: str
    base_url: str
    model: str
    has_key: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AiConfigOut(BaseModel):
    providers: list[AiProviderOut] = Field(default_factory=list)
    active_provider_id: str | None = None

    # 实际生效值（数据库 > 环境变量 > 默认值）
    effective_provider: AiProvider
    effective_base_url: str
    effective_model: str
    effective_api_key_set: bool = False
    api_key_source: Literal["db", "env", "none"] = "none"
