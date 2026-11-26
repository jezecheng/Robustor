"""ORM 表定义 —— 全项目唯一来源（16 张表）。其他 WP 只读，禁止修改。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.utcnow()


class Base(DeclarativeBase):
    pass


class Document(Base):
    """一次上传 = 一个 document。"""

    __tablename__ = "document"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    subject: Mapped[str] = mapped_column(String(32), default="math", index=True)
    source_name: Mapped[str] = mapped_column(String(255), default="")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Page(Base):
    __tablename__ = "page"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("document.id"), index=True)
    idx: Mapped[int] = mapped_column(Integer, default=1)
    image_path: Mapped[str] = mapped_column(String(512), default="")
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    rotation: Mapped[float] = mapped_column(Float, default=0.0)
    ink_profile_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")


class Region(Base):
    """证据层：页面上的一个块。bbox 恒为原图未旋转坐标系的归一化 [x, y, w, h]。"""

    __tablename__ = "region"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    page_id: Mapped[str] = mapped_column(ForeignKey("page.id"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("document.id"), index=True)
    problem_id: Mapped[str | None] = mapped_column(ForeignKey("problem.id"), nullable=True, index=True)
    block_type: Mapped[str] = mapped_column(String(16), default="stem")
    ink_role: Mapped[str | None] = mapped_column(String(16), nullable=True)
    bbox: Mapped[list] = mapped_column(JSON, default=list)
    page_start: Mapped[int] = mapped_column(Integer, default=1)
    page_end: Mapped[int] = mapped_column(Integer, default=1)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    order_idx: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text, default="")


class Problem(Base):
    __tablename__ = "problem"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("document.id"), index=True)
    subject: Mapped[str] = mapped_column(String(32), default="math", index=True)
    stem_latex: Mapped[str] = mapped_column(Text, default="")
    stem_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ProblemImage(Base):
    __tablename__ = "problem_image"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    problem_id: Mapped[str] = mapped_column(ForeignKey("problem.id"), index=True)
    region_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    image_path: Mapped[str] = mapped_column(String(512), default="")
    caption: Mapped[str] = mapped_column(String(255), default="")


class Solution(Base):
    __tablename__ = "solution"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    problem_id: Mapped[str] = mapped_column(ForeignKey("problem.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="student")
    latex: Mapped[str] = mapped_column(Text, default="")
    ink_role: Mapped[str] = mapped_column(String(16), default="answer")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)


class Mark(Base):
    __tablename__ = "mark"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    problem_id: Mapped[str | None] = mapped_column(ForeignKey("problem.id"), nullable=True, index=True)
    solution_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    region_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    verdict: Mapped[str] = mapped_column(String(16), default="unknown")
    raw_symbol: Mapped[str] = mapped_column(String(32), default="")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)


class Tag(Base):
    __tablename__ = "tag"
    __table_args__ = (UniqueConstraint("type", "normalized_name", name="uq_tag_type_name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    type: Mapped[str] = mapped_column(String(16), default="knowledge", index=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    normalized_name: Mapped[str] = mapped_column(String(128), default="")
    parent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)

    # 知识图谱扩展（来自 cn-math-taxonomy；手工标签这些字段为 NULL）
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    subject: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    domain: Mapped[str | None] = mapped_column(String(32), nullable=True)
    grade: Mapped[int | None] = mapped_column(Integer, nullable=True)
    semester: Mapped[str | None] = mapped_column(String(8), nullable=True)
    chapter: Mapped[str | None] = mapped_column(String(255), nullable=True)
    topic_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    mastery_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    diagnostic_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    standards_json: Mapped[list | None] = mapped_column(JSON, nullable=True)


class TagEdge(Base):
    """先修关系：from（前置知识点）→ to（后继知识点）。"""

    __tablename__ = "tag_edge"
    __table_args__ = (UniqueConstraint("from_tag_id", "to_tag_id", name="uq_tag_edge"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    from_tag_id: Mapped[str] = mapped_column(ForeignKey("tag.id"), index=True)
    to_tag_id: Mapped[str] = mapped_column(ForeignKey("tag.id"), index=True)
    strength: Mapped[str] = mapped_column(String(8), default="hard")
    reason: Mapped[str] = mapped_column(Text, default="")


class ProblemTag(Base):
    __tablename__ = "problem_tag"

    problem_id: Mapped[str] = mapped_column(ForeignKey("problem.id"), primary_key=True)
    tag_id: Mapped[str] = mapped_column(ForeignKey("tag.id"), primary_key=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(16), default="ai")


class InkProfile(Base):
    __tablename__ = "ink_profile"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(128), default="默认方案")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    rules_json: Mapped[dict] = mapped_column(JSON, default=dict)


class Review(Base):
    __tablename__ = "review"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    problem_id: Mapped[str] = mapped_column(ForeignKey("problem.id"), unique=True, index=True)
    ease: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, default=1)
    due_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    history_json: Mapped[list] = mapped_column(JSON, default=list)


class AiConfig(Base):
    """旧版全局 AI 配置（单行），仅用于迁移到 AiProvider。"""

    __tablename__ = "ai_config"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    provider: Mapped[str | None] = mapped_column(String(16), nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AiKey(Base):
    """旧版 Key 池（仅用于迁移）；api_key 为 Fernet 密文。"""

    __tablename__ = "ai_key"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(128), default="")
    api_key: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AiProvider(Base):
    """AI API 配置：名称 / Base URL / 模型 / Key 作为一个整体，同一时间只有一条 is_active。

    api_key 存 Fernet 密文，保存后接口不再返回任何形式的 Key 内容。
    """

    __tablename__ = "ai_provider"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(128), default="")
    base_url: Mapped[str] = mapped_column(String(512), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    api_key: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AiUsageLog(Base):
    """每次调用 AI Provider 的用量与结果，只追加不更新。

    provider_name / model 是请求发生时的快照：配置后续改名或删除，历史记录仍然可读。
    usage 字段统一按 OpenAI 兼容格式拆成 输入 / 输出 / 推理 / 缓存 四类。
    """

    __tablename__ = "ai_usage_log"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    scene: Mapped[str] = mapped_column(String(32), default="", index=True)
    provider_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_name: Mapped[str] = mapped_column(String(128), default="", index=True)
    model: Mapped[str] = mapped_column(String(128), default="", index=True)
    document_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)


class Job(Base):
    """document : job = 1 : 1，stage 为当前阶段。"""

    __tablename__ = "job"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("document.id"), index=True)
    stage: Mapped[str] = mapped_column(String(16), default="preprocess")
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
