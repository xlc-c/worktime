"""Segment labeling: cluster similar segments, then name each cluster.

Pure standard library (no numpy/scipy) so the tool can ship as a portable
folder on machines without admin rights.

Two labelers are available:
* deterministic - keyword/ID extraction, always works, no model needed;
* LLM - batches clusters into one prompt each, named by a local model.

Clustering: TF-IDF over character n-grams + tokens, sparse cosine similarity,
average-linkage agglomeration. A normal day (a few hundred segments) takes a
couple of seconds on a 4-core CPU.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter, defaultdict

from .llm import LlmClient, extract_json
from .util import domain_of, normalize_title

log = logging.getLogger("worktime.classify")

ID_RE = re.compile(
    r"(?<![A-Za-z0-9])("
    r"[A-Za-z]{1,8}[-_]?\d{4,}(?:[-_]\d{2,})?"
    r"|\d{4,}(?:[-_]\d{2,})+"
    r"|\d{8,}"
    r")(?![0-9])"
)
WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_.-]{2,}")
CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_STRIP_PREFIX = re.compile(r"^(re|fw|fwd|回复|转发)\s*[:：]\s*", re.I)
BROWSERS = {"Chrome", "Edge", "Firefox", "Brave", "Opera", "Vivaldi", "Chromium"}


def _cjk_ngrams(text: str) -> list[str]:
    grams: list[str] = []
    for run in CJK_RE.findall(text):
        if len(run) == 1:
            grams.append(run)
        for i in range(len(run) - 1):
            grams.append(run[i : i + 2])
        for token in re.split(r"[，。、；：！？（）()【】\[\]《》\s]+", run):
            if 2 <= len(token) <= 8:
                grams.append("w:" + token)
    return grams


def _clean_title(title: str, app: str) -> str:
    title = normalize_title(title or "")
    title = _STRIP_PREFIX.sub("", title)
    for sep in (" - ", " — ", " | "):
        if sep in title:
            first = title.split(sep)[0].strip()
            if first and first.lower() != (app or "").lower():
                return first
    return title.strip()


def primary_key(segment: dict) -> str:
    """Coarse identity of what is on screen: different primary keys are never
    clustered together unless clipboard glue explicitly links them."""
    title = _clean_title(segment.get("title", ""), segment.get("app", ""))
    page = (segment.get("page_title") or "").strip()
    if segment.get("app") in BROWSERS:
        return ("web:" + (page or title or segment.get("app", ""))).lower()[:80]
    return ("app:" + (segment.get("app", "") or "") + ":" + (title or "")).lower()[:80]


def tokens_for(segment: dict) -> list[str]:
    """Weight strong fields (app/title/filename/domain/IDs) above page prose.

    Without this, long page text and copied numbers make unrelated tasks look
    similar and the clustering over-merges.
    """
    strong = " ".join(
        p for p in (
            segment.get("title", ""),
            segment.get("page_title", ""),
            segment.get("url", ""),
            segment.get("app", ""),
            domain_of(segment.get("url", "")),
        ) if p
    )
    weak = " ".join(
        p for p in (
            segment.get("page_text", ""),
            segment.get("focused_text", ""),
            segment.get("clipboard_text", ""),
        ) if p
    )
    strong_tokens = _cjk_ngrams(strong) + [w.lower() for w in WORD_RE.findall(strong.lower())]
    strong_tokens += ["id:" + m.lower() for m in ID_RE.findall(strong)]
    weak_tokens = _cjk_ngrams(weak) + [w.lower() for w in WORD_RE.findall(weak.lower())]
    weak_tokens += ["id:" + m.lower() for m in ID_RE.findall(weak)]
    domain = domain_of(segment.get("url", ""))
    tokens = strong_tokens * 3 + weak_tokens + (["dom:" + domain] if domain else [])
    tokens.append("app:" + (segment.get("app") or "").lower())
    return tokens or ["empty"]


def _tfidf(segments: list[dict]) -> list[dict[str, float]]:
    token_lists = [tokens_for(s) for s in segments]
    n = len(segments)
    df: Counter = Counter()
    for tokens in token_lists:
        for token in set(tokens):
            df[token] += 1
    vectors: list[dict[str, float]] = []
    for tokens in token_lists:
        counts = Counter(tokens)
        total = sum(counts.values()) or 1
        vec: dict[str, float] = {}
        for token, count in counts.items():
            idf = math.log((1 + n) / (1 + df[token])) + 1.0
            vec[token] = (count / total) * idf
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        vectors.append({t: v / norm for t, v in vec.items()})
    return vectors


def _similarity_matrix(vectors: list[dict[str, float]]) -> list[list[float]]:
    n = len(vectors)
    sim = [[0.0] * n for _ in range(n)]
    inverted: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for idx, vec in enumerate(vectors):
        for token, weight in vec.items():
            inverted[token].append((idx, weight))
    for postings in inverted.values():
        for i in range(len(postings)):
            idx_i, weight_i = postings[i]
            for j in range(i + 1, len(postings)):
                idx_j, weight_j = postings[j]
                sim[idx_i][idx_j] += weight_i * weight_j
    for i in range(n):
        for j in range(i + 1, n):
            sim[j][i] = sim[i][j]
        sim[i][i] = 1.0
    return sim


def _average_linkage(sim: list[list[float]], threshold: float) -> list[list[int]]:
    n = len(sim)
    if n <= 1:
        return [[i] for i in range(n)]
    members: dict[int, list[int]] = {i: [i] for i in range(n)}
    sizes = {i: 1 for i in range(n)}
    active = list(range(n))
    mat = [row[:] for row in sim]
    for i in range(n):
        mat[i][i] = -1.0
    while len(active) > 1:
        best = -1.0
        bi = bj = -1
        for ai in range(len(active)):
            i = active[ai]
            row = mat[i]
            for aj in range(ai + 1, len(active)):
                j = active[aj]
                value = row[j]
                if value > best:
                    best = value
                    bi, bj = i, j
        if best < threshold or bi < 0:
            break
        a, b = bi, bj
        for other in active:
            if other in (a, b):
                continue
            merged = (sizes[a] * mat[a][other] + sizes[b] * mat[b][other]) / (
                sizes[a] + sizes[b]
            )
            mat[a][other] = mat[other][a] = merged
        sizes[a] += sizes[b]
        members[a].extend(members.pop(b))
        active.remove(b)
        for other in range(n):
            mat[b][other] = -1.0
            mat[other][b] = -1.0
    return [members[i] for i in active]


def _cluster(sim: list[list[float]], threshold: float,
             forced_groups: list[list[int]]) -> list[list[int]]:
    """Cluster indices, respecting pre-grouped indices (e.g. clipboard links)."""
    if not forced_groups:
        return _average_linkage(sim, threshold)
    groups: list[list[int]] = [list(g) for g in forced_groups if g]
    grouped = {i for g in groups for i in g}
    free = [i for i in range(len(sim)) if i not in grouped]
    if free:
        sub = [[sim[i][j] for j in free] for i in free]
        for cluster in _average_linkage(sub, threshold):
            groups.append([free[i] for i in cluster])
    return groups


def deterministic_label(segments: list[dict]) -> tuple[str, str, float]:
    ordered = sorted(segments, key=lambda s: -(s.get("duration_s") or 0))
    id_weights: Counter = Counter()
    for seg in ordered:
        duration = max(1.0, float(seg.get("duration_s") or 0))
        strong_text = " ".join(t for t in (
            seg.get("title", ""), seg.get("page_title", ""), seg.get("url", ""),
        ) if t)
        weak_text = " ".join(t for t in (
            seg.get("page_text", ""), seg.get("clipboard_text", ""),
            seg.get("focused_text", ""),
        ) if t)
        for found in ID_RE.findall(strong_text):
            id_weights[found] += duration * 3
        for found in ID_RE.findall(weak_text):
            id_weights[found] += duration
    top_id = id_weights.most_common(1)[0][0] if id_weights else ""

    task = ""
    for seg in ordered:
        candidate = _clean_title(seg.get("title", ""), seg.get("app", ""))
        if candidate and len(candidate) >= 2:
            task = candidate
            break
    if not task:
        for seg in ordered:
            candidate = (seg.get("page_title") or "").strip()
            if candidate:
                task = candidate
                break
    if not task:
        domains = [domain_of(seg.get("url", "")) for seg in ordered if seg.get("url")]
        task = domains[0] if domains else (ordered[0].get("app") or "未命名活动")
    if top_id and top_id.lower() not in task.lower():
        task = f"{task} [{top_id}]"
    if len(task) > 40:
        task = task[:40] + "…"
    matter = top_id if top_id else "未归类"
    return task, matter, 0.35


SYSTEM_PROMPT = (
    "你是工作时间分析助手。给定一段电脑活动证据，判断用户正在处理的具体任务"
    "以及它所属的事项（项目/客户/单据），只输出 JSON，不解释。"
)

USER_TEMPLATE = """下面是同一天中若干组电脑活动证据（每组已按相似度聚类）。请为每组给出：
- task：正在做的具体任务，8-20 个汉字，动词开头（如"核对华东贸易对账"）
- matter：所属事项/项目/客户名，无法判断填"未归类"
- confidence：0.0-1.0

输出格式：{{"items":[{{"id":1,"task":"...","matter":"...","confidence":0.8}}]}}

{payload}
"""


def _payload(clusters: list[list[dict]]) -> str:
    lines = []
    for idx, cluster in enumerate(clusters, start=1):
        lines.append(f"### 组 {idx}")
        for seg in cluster[:4]:
            lines.append("- " + (seg.get("evidence") or "")[:400])
    return "\n".join(lines)


def _llm_label(client: LlmClient, clusters: list[list[dict]],
               batch: int) -> list[tuple[str, str, float]] | None:
    results: list[tuple[str, str, float]] = []
    for start in range(0, len(clusters), max(1, batch)):
        chunk = clusters[start : start + max(1, batch)]
        try:
            content = client.chat(SYSTEM_PROMPT, USER_TEMPLATE.format(payload=_payload(chunk)))
            data = extract_json(content) or {}
            items = data.get("items") if isinstance(data, dict) else data
            if not isinstance(items, list):
                raise ValueError("no items")
            by_id = {}
            for item in items:
                if isinstance(item, dict) and "id" in item:
                    by_id[int(item["id"])] = item
            for local_id in range(1, len(chunk) + 1):
                item = by_id.get(local_id) or {}
                task = str(item.get("task") or "").strip()
                matter = str(item.get("matter") or "未归类").strip() or "未归类"
                conf = float(item.get("confidence") or 0.6)
                if not task:
                    raise ValueError("empty task")
                results.append((task[:40], matter[:40], max(0.0, min(1.0, conf))))
        except Exception as exc:
            log.warning("LLM labeling failed for batch at %s: %s", start, exc)
            return None
    return results


def _apply_alias(segment: dict, aliases: list[dict]) -> tuple[str, str] | None:
    title = (segment.get("title") or "").lower()
    url = (segment.get("url") or "").lower()
    domain = domain_of(segment.get("url") or "").lower()
    app = (segment.get("app") or "").lower()
    for alias in aliases:
        kind = (alias.get("kind") or "").lower()
        pattern = (alias.get("pattern") or "").lower()
        if not pattern:
            continue
        hit = False
        if kind == "title":
            hit = pattern in title
        elif kind == "url":
            hit = pattern in url
        elif kind == "domain":
            hit = pattern == domain
        elif kind == "app":
            hit = pattern == app
        if hit and (alias.get("task") or alias.get("matter")):
            return alias.get("task") or "", alias.get("matter") or "未归类"
    return None


def label_segments(segments: list[dict], cfg: dict, aliases: list[dict],
                   client: LlmClient | None) -> list[dict]:
    if not segments:
        return segments

    # 1. clipboard links are strong evidence of "same task"
    forced: dict[str, list[int]] = {}
    for idx, seg in enumerate(segments):
        link = seg.get("link_id") or ""
        if link:
            forced.setdefault(link, []).append(idx)

    # 2. aliases from previous reviews win immediately
    labels: dict[int, tuple[str, str, float]] = {}
    for idx, seg in enumerate(segments):
        hit = _apply_alias(seg, aliases)
        if hit:
            labels[idx] = (hit[0], hit[1], 0.99)

    vectors = _tfidf(segments)
    sim = _similarity_matrix(vectors)
    groups = _cluster(sim, float(cfg.get("cluster_threshold", 0.30)), list(forced.values()))

    # Split similarity clusters that contain multiple distinct "primary keys"
    # (e.g. two different Excel files) unless clipboard glue tied them together.
    split_groups: list[list[int]] = []
    for group in groups:
        linked = any(segments[i].get("link_id") for i in group)
        if linked or len(group) <= 1:
            split_groups.append(group)
            continue
        by_key: dict[str, list[int]] = {}
        for idx in group:
            by_key.setdefault(primary_key(segments[idx]), []).append(idx)
        split_groups.extend(by_key.values())
    groups = split_groups

    # attach alias-labeled indices to their own groups so they never get renamed
    final_groups: list[list[int]] = []
    for group in groups:
        aliased = [i for i in group if i in labels]
        if not aliased:
            final_groups.append(group)
            continue
        final_groups.append(aliased)
        rest = [i for i in group if i not in labels]
        if rest:
            final_groups.append(rest)

    pending = [g for g in final_groups if not any(i in labels for i in g)]
    pending.sort(key=lambda g: -sum(segments[i].get("duration_s", 0) for i in g))

    if client is not None and pending:
        result = _llm_label(client, [[segments[i] for i in g] for g in pending],
                            int(cfg.get("llm", {}).get("batch_clusters", 6)))
        if result is not None:
            for group, (task, matter, conf) in zip(pending, result):
                for idx in group:
                    labels[idx] = (task, matter, conf)

    for group in pending:
        if any(i in labels for i in group):
            continue
        cluster_segments = [segments[i] for i in group]
        task, matter, conf = deterministic_label(cluster_segments)
        for idx in group:
            labels.setdefault(idx, (task, matter, conf))

    for idx, seg in enumerate(segments):
        task, matter, conf = labels.get(idx, ("未归类", "未归类", 0.0))
        seg["auto_task"] = task
        seg["auto_matter"] = matter
        seg["confidence"] = round(float(conf), 2)
    return segments
