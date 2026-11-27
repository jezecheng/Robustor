"""主题分组（cluster）—— 在知识点之上再叠一层「一级簇 / 二级簇」语义分组。

数据位于 `taxonomy/clusters.json`，由 `scripts/ai_cluster.py` 基于全部知识点生成，
按知识点上游 id（external_id）挂载。分组只影响浏览与筛选，不改动先修边。
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

from .config import TAXONOMY_DIR

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_clusters() -> list[dict[str, Any]]:
    path = TAXONOMY_DIR / "clusters.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text("utf-8"))
    clusters = []
    for item in data.get("clusters", []):
        members = [str(ext) for ext in item.get("members", [])]
        if not members:
            continue
        clusters.append(
            {
                "id": str(item["id"]),
                "subject": str(item.get("subject") or ""),
                "parent": str(item.get("parent") or ""),
                "name": str(item["name"]),
                "members": members,
            }
        )
    return clusters


@lru_cache(maxsize=1)
def cluster_index() -> dict[str, tuple[str, str]]:
    """external_id -> (一级簇, 二级簇)。"""
    mapping: dict[str, tuple[str, str]] = {}
    for cluster in load_clusters():
        for ext in cluster["members"]:
            mapping.setdefault(ext, (cluster["parent"], cluster["name"]))
    return mapping


def cluster_names() -> dict[str, str]:
    """external_id -> 二级簇名。"""
    return {ext: pair[1] for ext, pair in cluster_index().items()}


def clusters_of(subject: str | None = None, parent: str | None = None) -> list[dict[str, Any]]:
    return [
        c
        for c in load_clusters()
        if (not subject or c["subject"] == subject) and (not parent or c["parent"] == parent)
    ]


def member_ids(cluster_id: str) -> list[str]:
    for cluster in load_clusters():
        if cluster["id"] == cluster_id:
            return list(cluster["members"])
    return []


def parent_member_ids(subject: str | None, parent: str) -> list[str]:
    """某个一级簇下全部知识点。"""
    members: list[str] = []
    for cluster in load_clusters():
        if cluster["parent"] != parent:
            continue
        if subject and cluster["subject"] != subject:
            continue
        members.extend(cluster["members"])
    return members


def cluster_name_of(external_id: str | None) -> str | None:
    if not external_id:
        return None
    pair = cluster_index().get(external_id)
    return pair[1] if pair else None


def cluster_parent_of(external_id: str | None) -> str | None:
    if not external_id:
        return None
    pair = cluster_index().get(external_id)
    return pair[0] if pair else None
