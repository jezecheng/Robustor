"""内置学科知识图谱（cn-math-taxonomy）导入。

数据位于仓库根目录 `taxonomy/`（CC BY-NC 4.0，覆盖 11 个学科），启动时幂等同步为
`tag` / `tag_edge`：
- 每个知识点是一条 `Tag(type="knowledge", status="approved")`，`external_id` 保存上游 id；
- 先修关系写入 `tag_edge`，from=前置知识点，to=后继知识点；
- 与种子词表同名的手工标签直接“收养”，不产生重复。
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

from sqlalchemy.orm import Session

from .config import TAXONOMY_DIR
from .models import Tag, TagEdge
from .textutil import normalize_name

log = logging.getLogger(__name__)

SUBJECT_LABELS = {
    "math": "数学",
    "chinese": "语文",
    "english": "英语",
    "physics": "物理",
    "chemistry": "化学",
    "biology": "生物",
    "history": "历史",
    "geography": "地理",
    "politics": "政治",
    "morality": "道德与法治",
    "science": "科学",
}
ID_PREFIX = {
    "cnm": "math",
    "cnc": "chinese",
    "cne": "english",
    "cnp": "physics",
    "cnk": "chemistry",
    "cnb": "biology",
    "cnh": "history",
    "cng": "geography",
    "cnz": "politics",
    "cnd": "morality",
    "cns": "science",
}


@lru_cache(maxsize=1)
def load_topics() -> list[dict[str, Any]]:
    path = TAXONOMY_DIR / "topics.json"
    if not path.exists():
        log.warning("未找到知识图谱数据：%s", path)
        return []
    return json.loads(path.read_text("utf-8"))


@lru_cache(maxsize=1)
def load_edges() -> list[dict[str, Any]]:
    path = TAXONOMY_DIR / "dependencies.json"
    if not path.exists():
        return []
    return json.loads(path.read_text("utf-8"))


@lru_cache(maxsize=1)
def load_meta() -> dict[str, Any]:
    path = TAXONOMY_DIR / "meta.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text("utf-8"))


def subject_of(topic: dict[str, Any]) -> str:
    subject = topic.get("subject")
    if subject:
        return str(subject)
    return ID_PREFIX.get(str(topic.get("id", "")).split("_")[0], "math")


def _apply(tag: Tag, topic: dict[str, Any], ext: str, name: str) -> None:
    tag.type = "knowledge"
    tag.name = name
    tag.normalized_name = normalize_name(name)
    tag.status = "approved"
    tag.external_id = ext
    tag.subject = subject_of(topic)
    tag.domain = topic.get("domain")
    grade = topic.get("grade")
    tag.grade = int(grade) if isinstance(grade, (int, float)) else None
    tag.semester = topic.get("semester")
    tag.chapter = topic.get("chapter")
    tag.topic_type = topic.get("type")
    tag.description = topic.get("description") or ""
    tag.mastery_json = topic.get("mastery_criteria") or []
    tag.diagnostic_json = topic.get("diagnostic_question") or {}
    tag.standards_json = topic.get("standards") or []


def _unique_name(
    topic: dict[str, Any],
    used: set[tuple[str, str]],
    owners: dict[tuple[str, str], str | None],
    subject: str,
) -> str:
    """同名知识点依次用学科、学段、章节、上游 id 后缀，保证唯一约束。"""
    name = str(topic["name"])
    key = ("knowledge", normalize_name(name))
    if key not in used:
        return name
    label = SUBJECT_LABELS.get(subject, subject)
    owner = owners.get(key)
    candidates = []
    if owner and owner != subject:
        candidates.append(f"{name}（{label}）")
    candidates.append(f"{name}（{topic.get('grade', '')}{topic.get('semester') or ''}）")
    candidates.append(f"{name}（{label}{topic.get('grade', '')}{topic.get('semester') or ''}）")
    chapter = str(topic.get("chapter") or "")[:40]
    if chapter:
        candidates.append(f"{name}（{chapter}）")
    candidates.append(f"{name}（{topic['id']}）")
    for candidate in candidates:
        if ("knowledge", normalize_name(candidate)) not in used:
            return candidate
    return candidates[-1]


def import_taxonomy(session: Session) -> dict[str, int]:
    topics = load_topics()
    if not topics:
        return {"topics": 0, "edges": 0, "created": 0, "adopted": 0}

    by_external: dict[str, Tag] = {
        tag.external_id: tag
        for tag in session.query(Tag).filter(Tag.external_id.is_not(None)).all()
    }
    # 只允许没有 external_id 的手工 / 种子标签被收养
    by_norm: dict[tuple[str, str], Tag] = {
        (tag.type, tag.normalized_name): tag
        for tag in session.query(Tag).filter(Tag.external_id.is_(None)).all()
    }
    owners: dict[tuple[str, str], str | None] = {
        (tag.type, tag.normalized_name): tag.subject for tag in session.query(Tag).all()
    }
    used: set[tuple[str, str]] = set(owners)

    created = adopted = 0
    for topic in topics:
        ext = str(topic["id"])
        subject = subject_of(topic)
        name = str(topic["name"])
        tag = by_external.get(ext)
        if tag is None:
            tag = by_norm.pop(("knowledge", normalize_name(name)), None)
            if tag is not None:
                adopted += 1
        if tag is None:
            tag = Tag(type="knowledge")
            session.add(tag)
            created += 1
            name = _unique_name(topic, used, owners, subject)
        elif normalize_name(name) != tag.normalized_name:
            # 上游改名：若新名已被别的标签占用，保留可读后缀
            old = (tag.type, tag.normalized_name)
            used.discard(old)
            owners.pop(old, None)
            name = _unique_name(topic, used, owners, subject)
        _apply(tag, topic, ext, name)
        key = ("knowledge", tag.normalized_name)
        used.add(key)
        owners[key] = subject
        by_external[ext] = tag

    session.flush()

    existing_edges = {
        (row[0], row[1]) for row in session.query(TagEdge.from_tag_id, TagEdge.to_tag_id).all()
    }
    linked = 0
    for edge in load_edges():
        source = by_external.get(str(edge.get("prerequisiteId")))
        target = by_external.get(str(edge.get("topicId")))
        if source is None or target is None or source.id == target.id:
            continue
        pair = (source.id, target.id)
        if pair in existing_edges:
            continue
        session.add(
            TagEdge(
                from_tag_id=source.id,
                to_tag_id=target.id,
                strength=edge.get("strength") or "hard",
                reason=edge.get("reason") or "",
            )
        )
        existing_edges.add(pair)
        linked += 1

    session.commit()
    result = {
        "topics": len(topics),
        "edges": linked,
        "created": created,
        "adopted": adopted,
    }
    log.info("知识图谱同步完成：%s", result)
    return result
