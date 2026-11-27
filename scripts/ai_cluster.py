"""AI 重新分簇：把全部学科知识点组织为一级簇 / 二级簇，写回 taxonomy/clusters.json。

流程（每个学科独立）：
1. 设计结构：把该学科全部知识点按现有领域分组交给模型，生成 4-10 个一级簇，
   每个一级簇下 3-8 个二级簇；
2. 批量归类：把知识点按批交给模型，分配到二级簇（只允许选给定簇）；
3. 校验覆盖：未归类的知识点自动补充分配，保证每个知识点恰好属于一个二级簇。

中间结果缓存在 /tmp/robustor_cluster_cache，支持断点续跑。

用法：
    cd Robustor && apps/api/.venv/bin/python scripts/ai_cluster.py
    apps/api/.venv/bin/python scripts/ai_cluster.py --subjects math,physics
    apps/api/.venv/bin/python scripts/ai_cluster.py --no-cache   # 忽略缓存重新生成
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.ai_config import effective  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.pipeline.providers.chat import ChatProvider  # noqa: E402

TAXONOMY_DIR = ROOT / "taxonomy"
CACHE_DIR = Path("/tmp/robustor_cluster_cache")
BATCH_SIZE = 80
WORKERS = 3
RETRIES = 4

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

SYSTEM = "你是中国基础教育课程标准与知识图谱专家。只输出 JSON，不要输出解释或 Markdown 代码块。"


def load_topics() -> list[dict[str, Any]]:
    return json.loads((TAXONOMY_DIR / "topics.json").read_text("utf-8"))


def cache_path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{name}.json"


def read_cache(name: str) -> Any | None:
    path = cache_path(name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text("utf-8"))
    except json.JSONDecodeError:
        return None


def write_cache(name: str, data: Any) -> None:
    cache_path(name).write_text(json.dumps(data, ensure_ascii=False), "utf-8")


def call_json(provider: ChatProvider, user: str) -> dict[str, Any]:
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            return provider.complete_json(SYSTEM, user)
        except Exception as exc:  # noqa: BLE001 - 网络/解析失败统一重试
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"AI 调用失败：{last}")


def topic_line(topic: dict[str, Any]) -> str:
    grade = topic.get("grade")
    grade_text = f"{grade}年级" if grade is not None else "未分级"
    return f"{topic['id']}｜{topic['name']}｜{topic.get('domain') or '未分领域'}｜{grade_text}"


def design_prompt(subject: str, topics: list[dict[str, Any]]) -> str:
    label = SUBJECT_LABELS.get(subject, subject)
    domain_counter = Counter(topic.get("domain") or "未分领域" for topic in topics)
    domains = "、".join(f"{name}({count})" for name, count in domain_counter.most_common())
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for topic in topics:
        grouped[topic.get("domain") or "未分领域"].append(topic)
    blocks = []
    for domain, items in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        lines = "\n".join(f"- {topic['name']}（{topic.get('grade')}年级）" for topic in sorted(
            items, key=lambda t: (t.get("grade") or 0, t["name"])
        ))
        blocks.append(f"### 现有领域：{domain}（{len(items)} 个）\n{lines}")
    return f"""学科：{label}（{subject}），共 {len(topics)} 个知识点。
现有领域分布（仅作参考，可以重新组织）：{domains}

请基于这些知识点重新设计一套两级主题簇结构：
- 一级簇 4-10 个，名称简洁、互不重叠，覆盖整个学科；
- 每个一级簇下 3-8 个二级簇，名称具体、能体现知识点共性；
- 每个二级簇应能容纳约 10-60 个知识点，避免过细或过粗；
- 只依据知识点本身的含义分簇，不要按年级或教材单元划分。

知识点清单（按现有领域分组）：
{chr(10).join(blocks)}

只输出如下 JSON：
{{"clusters":[{{"name":"一级簇名称","description":"一句话说明","children":[{{"name":"二级簇名称","description":"一句话说明"}}]}}]}}"""


def assignment_prompt(
    subject: str, clusters: list[dict[str, Any]], batch: list[dict[str, Any]]
) -> str:
    label = SUBJECT_LABELS.get(subject, subject)
    cluster_lines = []
    for cluster in clusters:
        cluster_lines.append(f"{cluster['id']}｜{cluster['parent']} / {cluster['name']}｜{cluster['description']}")
    lines = "\n".join(topic_line(topic) for topic in batch)
    return f"""学科：{label}。请把下面每个知识点分配到给定的二级簇（只能从簇列表中选择，必须覆盖每一个知识点 id）。

二级簇列表（格式：簇 id｜一级簇 / 二级簇｜说明）：
{chr(10).join(cluster_lines)}

知识点（格式：id｜名称｜现有领域｜年级）：
{lines}

只输出如下 JSON：
{{"assignments":{{"知识点 id":"簇 id"}}}}"""


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def normalize_structure(subject: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("clusters")
    if not isinstance(raw, list) or not raw:
        raise ValueError("结构为空")
    clusters: list[dict[str, Any]] = []
    used_parents: set[str] = set()
    for i, parent in enumerate(raw, start=1):
        if not isinstance(parent, dict):
            continue
        parent_name = str(parent.get("name") or "").strip()
        if not parent_name:
            continue
        if parent_name in used_parents:
            parent_name = f"{parent_name}{i}"
        used_parents.add(parent_name)
        children = parent.get("children") or []
        used_names: set[str] = set()
        for j, child in enumerate(children, start=1):
            if not isinstance(child, dict):
                continue
            name = str(child.get("name") or "").strip()
            if not name:
                continue
            if name in used_names:
                name = f"{name}{j}"
            used_names.add(name)
            clusters.append(
                {
                    "id": f"{subject}-{i:02d}-{j:02d}",
                    "subject": subject,
                    "parent": parent_name,
                    "name": name,
                    "description": str(child.get("description") or "").strip(),
                }
            )
    if not clusters:
        raise ValueError("没有可用的二级簇")
    return clusters


def fallback_clusters(subject: str, topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """结构生成失败时：用现有领域作为一级簇，领域本身作为二级簇。"""
    domains = sorted({topic.get("domain") or "其他" for topic in topics})
    return [
        {
            "id": f"{subject}-{i:02d}-01",
            "subject": subject,
            "parent": domain,
            "name": domain,
            "description": domain,
        }
        for i, domain in enumerate(domains, start=1)
    ] or [
        {
            "id": f"{subject}-01-01",
            "subject": subject,
            "parent": "综合",
            "name": "综合",
            "description": "综合",
        }
    ]


def structure_of(
    provider: ChatProvider, subject: str, topics: list[dict[str, Any]], use_cache: bool
) -> list[dict[str, Any]]:
    cached = read_cache(f"structure_{subject}") if use_cache else None
    if cached:
        return cached
    try:
        payload = call_json(provider, design_prompt(subject, topics))
        clusters = normalize_structure(subject, payload)
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] {subject} 结构生成失败，回落现有领域：{exc}", flush=True)
        clusters = fallback_clusters(subject, topics)
    write_cache(f"structure_{subject}", clusters)
    return clusters


def assign_batch(
    provider: ChatProvider,
    subject: str,
    clusters: list[dict[str, Any]],
    batch: list[dict[str, Any]],
    use_cache: bool,
    index: int,
) -> dict[str, str]:
    name = f"assign_{subject}_{index:03d}"
    cached = read_cache(name) if use_cache else None
    if cached:
        return cached
    valid = {cluster["id"] for cluster in clusters}
    batch_ids = {topic["id"] for topic in batch}
    result: dict[str, str] = {}
    for attempt in range(2):
        pending = [topic for topic in batch if topic["id"] not in result]
        if not pending:
            break
        payload = call_json(provider, assignment_prompt(subject, clusters, pending))
        assignments = payload.get("assignments")
        if not isinstance(assignments, dict):
            continue
        for topic_id, cluster_id in assignments.items():
            if topic_id in batch_ids and str(cluster_id) in valid:
                result[topic_id] = str(cluster_id)
    write_cache(name, result)
    return result


def assign_subject(
    provider: ChatProvider, subject: str, topics: list[dict[str, Any]], clusters: list[dict[str, Any]],
    use_cache: bool,
) -> dict[str, str]:
    batches = [topics[i : i + BATCH_SIZE] for i in range(0, len(topics), BATCH_SIZE)]
    assignments: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(assign_batch, provider, subject, clusters, batch, use_cache, idx): idx
            for idx, batch in enumerate(batches)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                assignments.update(future.result())
            except Exception as exc:  # noqa: BLE001
                print(f"  [warn] {subject} 第 {idx} 批归类失败：{exc}", flush=True)

    missing = [topic for topic in topics if topic["id"] not in assignments]
    if missing:
        print(f"  [warn] {subject} 有 {len(missing)} 个知识点未归类，按领域兜底", flush=True)
        by_domain: dict[str, Counter[str]] = defaultdict(Counter)
        for topic in topics:
            cluster_id = assignments.get(topic["id"])
            if cluster_id:
                by_domain[topic.get("domain") or ""][cluster_id] += 1
        largest = Counter(assignments.values()).most_common(1)
        default_id = largest[0][0] if largest else clusters[0]["id"]
        for topic in missing:
            domain = topic.get("domain") or ""
            assignments[topic["id"]] = by_domain[domain].most_common(1)[0][0] if by_domain[domain] else default_id
    return assignments


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subjects", default="", help="逗号分隔的学科 key，默认全部")
    parser.add_argument("--no-cache", action="store_true", help="忽略缓存重新生成")
    args = parser.parse_args()
    use_cache = not args.no_cache

    topics = load_topics()
    by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for topic in topics:
        by_subject[topic.get("subject") or "unknown"].append(topic)

    wanted = [item.strip() for item in args.subjects.split(",") if item.strip()]
    subjects = wanted or sorted(by_subject)

    with SessionLocal() as session:
        cfg = effective(session)
    if not cfg.get("api_key"):
        print("未找到可用的 AI Key，无法执行分簇", flush=True)
        return 1
    provider = ChatProvider(cfg["api_key"], cfg["base_url"], cfg["model"], timeout=180)
    print(f"使用模型 {cfg['model']}，学科：{', '.join(subjects)}", flush=True)

    output: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}
    for subject in subjects:
        subject_topics = by_subject.get(subject) or []
        if not subject_topics:
            print(f"[skip] {subject} 没有知识点", flush=True)
            continue
        started = time.perf_counter()
        clusters = structure_of(provider, subject, subject_topics, use_cache)
        print(
            f"[{SUBJECT_LABELS.get(subject, subject)}] 结构 {len(clusters)} 个二级簇，"
            f"开始归类 {len(subject_topics)} 个知识点…",
            flush=True,
        )
        assignments = assign_subject(provider, subject, subject_topics, clusters, use_cache)
        members: dict[str, list[str]] = defaultdict(list)
        for topic in subject_topics:
            members[assignments[topic["id"]]].append(topic["id"])
        kept = 0
        for cluster in clusters:
            ids = members.get(cluster["id"]) or []
            if not ids:
                continue
            kept += 1
            output.append(
                {
                    "id": cluster["id"],
                    "subject": subject,
                    "parent": cluster["parent"],
                    "name": cluster["name"],
                    "description": cluster.get("description") or "",
                    "members": ids,
                }
            )
        stats[subject] = {
            "topics": len(subject_topics),
            "parents": len({cluster["parent"] for cluster in clusters}),
            "clusters": kept,
            "seconds": round(time.perf_counter() - started, 1),
        }
        print(f"  完成：{stats[subject]}", flush=True)

    path = TAXONOMY_DIR / "clusters.json"
    if path.exists():
        backup = Path("/tmp/robustor-clusters-backup.json")
        if not backup.exists():
            backup.write_text(path.read_text("utf-8"), "utf-8")
    path.write_text(
        json.dumps({"version": 2, "generated_by": cfg["model"], "clusters": output}, ensure_ascii=False, indent=2),
        "utf-8",
    )
    print(f"已写入 {path}：{len(output)} 个二级簇", flush=True)
    print(json.dumps(stats, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
