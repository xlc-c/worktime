"""Turn raw capture rows into a single timeline of coherent segments.

Rules (all deterministic, no AI):
1. Tile raw samples into spans until the next sample.
2. Merge consecutive spans with the same app/window title.
3. Absorb very short spans (quick app switches) into their neighbour.
4. Attach browser page context (URL/title/visible text) from the extension,
   splitting a browser span when the page URL changes.
5. Use copy/paste pairs as "task glue": copy in one app + paste in another
   within a few minutes -> same link id (same task).
"""

from __future__ import annotations

import bisect
import uuid
from datetime import datetime, timedelta

from .util import domain_of, normalize_title, ts_to_dt

BROWSERS = {"Chrome", "Edge", "Firefox", "Brave", "Opera", "Vivaldi", "Chromium"}


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _to_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return ts_to_dt(str(value))


def _bisect_ts(rows: list[dict], key: str, dt: datetime) -> int:
    """Index of the last row whose key is <= dt."""
    stamps = [row[key] for row in rows]
    return bisect.bisect_right(stamps, _iso(dt)) - 1


def _focus_for(app: str, start: datetime, focus: list[dict]) -> str:
    if not focus:
        return ""
    idx = _bisect_ts(focus, "ts", start + timedelta(seconds=5))
    lo = max(0, idx - 10)
    for row in range(idx, lo - 1, -1):
        candidate = focus[row]
        if (candidate.get("app") or "") != app:
            continue
        cand_dt = _to_dt(candidate["ts"])
        if cand_dt < start - timedelta(seconds=40):
            break
        return candidate.get("text_preview") or ""
    return ""


def _clip_in_range(clip: list[dict], start: datetime, end: datetime) -> list[dict]:
    base = _bisect_ts(clip, "ts", start - timedelta(seconds=10))
    out = []
    low = start - timedelta(seconds=10)
    high = end + timedelta(seconds=10)
    for row in range(max(0, base), len(clip)):
        event = clip[row]
        event_dt = _to_dt(event["ts"])
        if event_dt < low:
            continue
        if event_dt > high:
            break
        out.append(event)
    return out


def _build_tiles(raw: list[dict], cfg: dict) -> list[dict]:
    idle_thr = float(cfg.get("idle_threshold_s", 120))
    heartbeat = float(cfg.get("heartbeat_s", 20))
    rows = [
        r
        for r in raw
        if (r.get("screen") or "active") == "active"
        and float(r.get("idle_sec") or 0) < idle_thr
    ]
    tiles: list[dict] = []
    for i, row in enumerate(rows):
        start = _to_dt(row["ts"])
        if i + 1 < len(rows):
            nxt = _to_dt(rows[i + 1]["ts"])
            gap = (nxt - start).total_seconds()
            end = nxt if gap <= idle_thr else start + timedelta(seconds=heartbeat)
        else:
            end = start + timedelta(seconds=heartbeat)
        if end <= start:
            continue
        tiles.append(
            {
                "start": start,
                "end": end,
                "app": row.get("app") or "unknown",
                "title": normalize_title(row.get("title") or ""),
                "proc": row.get("proc") or "",
            }
        )
    return tiles


def _merge_same_key(tiles: list[dict], gap_fill: float) -> list[dict]:
    merged: list[dict] = []
    for tile in tiles:
        if not merged:
            merged.append(dict(tile))
            continue
        prev = merged[-1]
        same = (prev["app"], prev["title"]) == (tile["app"], tile["title"])
        gap = (tile["start"] - prev["end"]).total_seconds()
        if same and gap <= gap_fill:
            prev["end"] = tile["end"]
        else:
            merged.append(dict(tile))
    return merged


def _absorb_short(segments: list[dict], min_seconds: float, gap_fill: float) -> list[dict]:
    out: list[dict] = []
    for seg in segments:
        duration = (seg["end"] - seg["start"]).total_seconds()
        if out and duration < min_seconds:
            out[-1]["end"] = max(out[-1]["end"], seg["end"])
            if seg.get("app") == out[-1].get("app"):
                out[-1]["title"] = out[-1].get("title") or seg.get("title")
            continue
        out.append(seg)
    return _merge_same_key(out, gap_fill)


def _split_long(segments: list[dict], max_seconds: float) -> list[dict]:
    if max_seconds <= 0:
        return segments
    out: list[dict] = []
    for seg in segments:
        duration = (seg["end"] - seg["start"]).total_seconds()
        if duration <= max_seconds:
            out.append(seg)
            continue
        parts = int(duration // max_seconds) + (1 if duration % max_seconds else 0)
        step = duration / parts
        for i in range(parts):
            start = seg["start"] + timedelta(seconds=step * i)
            end = seg["start"] + timedelta(seconds=step * (i + 1))
            clone = dict(seg)
            clone["start"] = start
            clone["end"] = end
            out.append(clone)
    return out


def _web_events_for(app: str, start: datetime, end: datetime,
                    web: list[dict], carry_s: int) -> list[dict]:
    if app not in BROWSERS or not web:
        return []
    low = start - timedelta(seconds=carry_s)
    high = end + timedelta(seconds=5)
    idx = _bisect_ts(web, "ts", high)
    out: list[dict] = []
    row = idx
    while row >= 0:
        event = web[row]
        event_dt = _to_dt(event["ts"])
        if event_dt < low:
            break
        if (event.get("browser") or "") == app:
            out.append(event)
        row -= 1
    out.reverse()
    return out


def _attach_web(segments: list[dict], web: list[dict], window_s: int) -> list[dict]:
    """Attach page context; split a browser segment when the URL changes."""
    carry = max(int(window_s), 600)
    out: list[dict] = []
    for seg in segments:
        if seg["app"] not in BROWSERS:
            seg.update(url="", page_title="", page_text="")
            out.append(seg)
            continue
        events = _web_events_for(seg["app"], seg["start"], seg["end"], web, carry)
        if not events:
            seg.update(url="", page_title="", page_text="")
            out.append(seg)
            continue

        groups: list[dict] = []
        current = None
        for event in events:
            event_dt = _to_dt(event["ts"])
            if current is None or event.get("url") != current["url"]:
                if current is not None:
                    groups.append(current)
                current = {
                    "url": event.get("url") or "",
                    "page_title": event.get("page_title") or "",
                    "page_text": event.get("visible_text") or "",
                    "start": seg["start"] if not groups else max(seg["start"], event_dt),
                }
            else:
                current["page_title"] = event.get("page_title") or current["page_title"]
                current["page_text"] = event.get("visible_text") or current["page_text"]
        groups.append(current)

        for gi, group in enumerate(groups):
            group["end"] = groups[gi + 1]["start"] if gi + 1 < len(groups) else seg["end"]
        groups = [g for g in groups if g["end"] > g["start"]]
        if not groups:
            seg.update(url="", page_title="", page_text="")
            out.append(seg)
            continue
        for group in groups:
            clone = dict(seg)
            clone["start"] = group["start"]
            clone["end"] = group["end"]
            clone["url"] = group["url"]
            clone["page_title"] = group["page_title"]
            clone["page_text"] = group["page_text"]
            out.append(clone)
    return out


def _link_by_clipboard(segments: list[dict], clip: list[dict], glue_window: int) -> None:
    by_hash: dict[str, list[dict]] = {}
    for event in clip:
        digest = event.get("text_hash") or ""
        if not digest:
            continue
        by_hash.setdefault(digest, []).append(event)

    for events in by_hash.values():
        if len(events) < 2:
            continue
        for first, second in zip(events, events[1:]):
            span_start = _to_dt(first["ts"]) - timedelta(seconds=3)
            span_end = _to_dt(second["ts"]) + timedelta(seconds=5)
            if (span_end - span_start).total_seconds() > glue_window:
                continue
            link_id = "L" + uuid.uuid4().hex[:10]
            touched = False
            for seg in segments:
                if seg["start"] <= span_end and seg["end"] >= span_start:
                    if not seg.get("link_id"):
                        seg["link_id"] = link_id
                        touched = True
            if not touched:
                continue


def _evidence(seg: dict) -> str:
    parts = [f"应用={seg.get('app', '')}", f"窗口={seg.get('title', '')}"]
    if seg.get("page_title"):
        parts.append(f"网页={seg['page_title'][:120]}")
    if seg.get("page_text"):
        parts.append(f"页面内容={seg['page_text'][:200]}")
    if seg.get("url"):
        parts.append(f"网址={domain_of(seg['url'])} {seg['url'][:100]}")
    if seg.get("focused_text"):
        parts.append(f"焦点内容={seg['focused_text'][:180]}")
    if seg.get("clipboard_text"):
        parts.append(f"剪贴板={seg['clipboard_text'][:180]}")
    return " | ".join(parts)


def build_segments(raw: list[dict], web: list[dict], clip: list[dict],
                   focus: list[dict], cfg: dict) -> list[dict]:
    tiles = _build_tiles(raw, cfg)

    merged = _merge_same_key(tiles, float(cfg.get("gap_fill_s", 5)))
    merged = _absorb_short(
        merged,
        float(cfg.get("report", {}).get("min_segment_s", 15)),
        float(cfg.get("gap_fill_s", 5)),
    )
    merged = _split_long(merged, float(cfg.get("max_segment_minutes", 45)) * 60)
    merged = _attach_web(merged, web, int(cfg.get("web_match_window_s", 20)))

    for seg in merged:
        seg["focused_text"] = _focus_for(seg["app"], seg["start"], focus)
        clips = _clip_in_range(clip, seg["start"], seg["end"])
        previews = []
        for event in clips:
            preview = (event.get("preview") or "").strip()
            if preview and preview not in previews:
                previews.append(preview)
        seg["clipboard_text"] = " | ".join(previews[-2:])[:300]
        seg["evidence"] = _evidence(seg)

    _link_by_clipboard(merged, clip, int(cfg.get("glue_window_s", 300)))

    segments = []
    for seg in merged:
        duration = (seg["end"] - seg["start"]).total_seconds()
        if duration <= 0:
            continue
        segments.append(
            {
                "start_ts": _iso(seg["start"]),
                "end_ts": _iso(seg["end"]),
                "duration_s": duration,
                "kind": "work",
                "app": seg["app"],
                "title": seg["title"],
                "url": seg.get("url", ""),
                "page_title": seg.get("page_title", ""),
                "page_text": seg.get("page_text", ""),
                "focused_text": seg.get("focused_text", ""),
                "clipboard_text": seg.get("clipboard_text", ""),
                "link_id": seg.get("link_id", ""),
                "evidence": seg.get("evidence", ""),
            }
        )
    segments.sort(key=lambda s: s["start_ts"])
    return segments
