"""Explicit user rules: deterministic "this activity belongs to that matter".

Automatic clustering is good at naming, bad at consistency: the same client can
land in three different clusters on three different days. Rules close that gap.

A rule has zero or more conditions (app / title / url_domain / focused text).
All conditions that are set must match (AND). Syntax per condition:

* ``text``      case-insensitive substring (default)
* ``=text``     exact match, case-insensitive
* ``re:expr``   Python regular expression, case-insensitive

Rules run before clustering and before learned aliases, so they act as a
deterministic baseline; a manual label always wins (it is not stored here).

The module is pure standard library and has no Windows dependency, so it is
covered by unit tests on any platform.
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger("worktime.rules")

CONDITION_FIELDS = ("app", "title", "url_domain", "focused")


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _matches(pattern: str, value: str) -> bool:
    pattern = str(pattern or "").strip()
    if not pattern:
        return True
    if pattern.startswith("re:"):
        try:
            return re.search(pattern[3:], value or "", re.IGNORECASE) is not None
        except re.error:
            return False
    if pattern.startswith("="):
        return _norm(value) == _norm(pattern[1:])
    return _norm(pattern) in _norm(value)


def has_conditions(rule: dict) -> bool:
    return any(str(rule.get(field) or "").strip() for field in CONDITION_FIELDS)


def rule_matches(rule: dict, seg: dict) -> bool:
    """True when every condition in ``rule`` matches ``seg`` and at least one is set."""
    if not has_conditions(rule):
        return False
    if not _matches(rule.get("app"), seg.get("app") or ""):
        return False
    title_text = " ".join(t for t in (
        seg.get("title") or "", seg.get("page_title") or "",
    ) if t)
    if not _matches(rule.get("title"), title_text):
        return False
    url_text = " ".join(t for t in (seg.get("url") or "", seg.get("page_title") or "") if t)
    if not _matches(rule.get("url_domain"), url_text):
        return False
    if not _matches(rule.get("focused"), seg.get("focused_text") or ""):
        return False
    return True


def sort_rules(rules: list[dict]) -> list[dict]:
    return sorted(
        [r for r in (rules or []) if int(r.get("enabled", 1) or 0)],
        key=lambda r: (-int(r.get("priority") or 100), int(r.get("id") or 0)),
    )


def _display_task(seg: dict) -> str:
    """A short human-readable task when a rule only names the matter."""
    title = str(seg.get("page_title") or seg.get("title") or "").strip()
    for sep in (" - ", " — ", " | "):
        if sep in title:
            title = title.split(sep)[0].strip()
            break
    title = re.sub(r"^(re|fw|fwd|回复|转发)\s*[:：]\s*", "", title, flags=re.I).strip()
    if title:
        return title[:40]
    return (seg.get("app") or "未命名活动")[:40]


def apply_rules(segments: list[dict], rules: list[dict]) -> dict:
    """Label segments from rules in place. Returns {rule_id: hit_count}."""
    hits: dict[int, int] = {}
    ordered = sort_rules(rules)
    if not ordered:
        return hits
    for seg in segments:
        for rule in ordered:
            if not rule_matches(rule, seg):
                continue
            matter = str(rule.get("matter") or "").strip()
            task = str(rule.get("task") or "").strip()
            if not matter and not task:
                continue
            seg["auto_matter"] = matter or seg.get("auto_matter") or "未归类"
            seg["auto_task"] = task or _display_task(seg)
            seg["confidence"] = max(float(seg.get("confidence") or 0.0), 0.95)
            seg["rule_name"] = str(rule.get("name") or "")
            rule_id = int(rule.get("id") or 0)
            if rule_id:
                hits[rule_id] = hits.get(rule_id, 0) + 1
            break
    return hits


def preview_rule(rule: dict, segments: list[dict], limit: int = 5) -> dict:
    """Dry-run a rule against a day's segments (used by the UI/CLI test command)."""
    matched = [s for s in segments if rule_matches(rule, s)]
    total = sum(float(s.get("duration_s") or 0) for s in matched)
    return {
        "count": len(matched),
        "seconds": round(total, 1),
        "samples": [
            {
                "start": s.get("start_ts", "")[11:16],
                "end": s.get("end_ts", "")[11:16],
                "app": s.get("app", ""),
                "title": (s.get("title") or "")[:60],
            }
            for s in matched[:limit]
        ],
    }


def suggest_rule(seg: dict, matter: str = "", task: str = "") -> dict:
    """Build a starter rule from an existing segment (app + domain or title)."""
    app = (seg.get("app") or "").strip()
    rule = {"name": "", "app": "", "title": "", "url_domain": "", "focused": "",
            "matter": matter, "task": task, "priority": 100, "enabled": True}
    from .util import domain_of

    domain = domain_of(seg.get("url") or "")
    title = (seg.get("title") or "").strip()
    for sep in (" - ", " — ", " | "):
        if sep in title:
            title = title.split(sep)[0].strip()
            break
    title = re.sub(r"^(re|fw|fwd|回复|转发)\s*[:：]\s*", "", title, flags=re.I).strip()
    # drop a document extension so the same rule also matches "对账单(2).xlsx"
    title = re.sub(r"\.(xlsx|xls|docx|doc|pptx|ppt|pdf|txt|csv)$", "", title,
                   flags=re.I).strip()

    if domain:
        rule["url_domain"] = domain
        rule["name"] = f"{domain} → {matter or '未命名事项'}"
    elif title and len(title) >= 2:
        rule["title"] = title[:60]
        rule["name"] = f"{title[:24]} → {matter or '未命名事项'}"
    elif app:
        rule["app"] = app
        rule["name"] = f"{app} → {matter or '未命名事项'}"
    else:
        rule["name"] = matter or "未命名规则"
    return rule
