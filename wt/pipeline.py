"""Daily pipeline: raw capture -> segments -> labels -> stored timeline."""

from __future__ import annotations

import logging

from .classify import label_segments
from .llm import LlmClient
from .segment import build_segments
from .store import Store
from .util import day_bounds, now_iso

log = logging.getLogger("worktime.pipeline")


def _preserve_manual_labels(new_segments: list[dict], old_segments: list[dict]) -> None:
    """Carry over labels the user confirmed during review, matched by time overlap."""
    manual = [
        s for s in old_segments
        if (s.get("final_task") or s.get("final_matter"))
        and (s.get("final_task") or "") != (s.get("auto_task") or "")
    ]
    for seg in new_segments:
        for old in manual:
            if seg["start_ts"] < old["end_ts"] and seg["end_ts"] > old["start_ts"]:
                seg["final_task"] = old.get("final_task") or ""
                seg["final_matter"] = old.get("final_matter") or ""
                break


def process_date(store: Store, cfg: dict, date: str, use_llm: bool = True) -> dict:
    start, end = day_bounds(date)
    raw = store.fetch_raw(start, end)
    web = store.fetch_web(start, end)
    clip = store.fetch_clip(start, end)
    focus = store.fetch_focus(start, end)
    if not raw:
        log.warning("no raw activity for %s", date)
        return {"date": date, "segments": 0, "active_s": 0.0, "matters": 0}

    old_segments = store.list_segments(date)
    segments = build_segments(raw, web, clip, focus, cfg)
    for seg in segments:
        seg["date"] = date
    _preserve_manual_labels(segments, old_segments)

    client = None
    if use_llm and cfg.get("llm", {}).get("enabled"):
        candidate = LlmClient(cfg)
        if candidate.health():
            client = candidate
            log.info("local LLM available at %s", candidate.base_url)
        else:
            log.warning("LLM enabled but not reachable at %s; using deterministic labels",
                        candidate.base_url)

    rules = store.list_rules(only_enabled=True)
    label_segments(segments, cfg, store.get_aliases(), client, rules)

    for rule_id, count in (cfg.get("_rule_hits") or {}).items():
        if count:
            store.mark_rule_hit(int(rule_id), int(count), now_iso())

    for seg in segments:
        if not seg.get("final_task"):
            seg["final_task"] = seg.get("auto_task") or "未归类"
        if not seg.get("final_matter"):
            seg["final_matter"] = seg.get("auto_matter") or "未归类"

    store.replace_segments(date, segments)
    store.mark_processed(date, now_iso())

    active = sum(s["duration_s"] for s in segments)
    matters = {s.get("final_matter") or "未归类" for s in segments}
    result = {
        "date": date,
        "segments": len(segments),
        "active_s": round(active, 1),
        "matters": len(matters),
        "llm": client is not None,
        "rules_hit": sum(int(v) for v in (cfg.get("_rule_hits") or {}).values()),
    }
    log.info("processed %s: %s", date, result)
    return result
