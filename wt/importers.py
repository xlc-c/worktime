"""Import raw activity captured by other platforms (Android app, scripts).

Contract: ``worktime-raw`` v1 — see docs/PLATFORMS.md.

    {
      "format": "worktime-raw", "version": 1, "platform": "android",
      "device": {"id": "...", "name": "..."},
      "days": {"2026-11-13": {"activity": [...], "focus": [...]}}
    }

Only event rows move across platforms; segmentation, labeling, reports and
billing stay in the shared Python core so every platform has identical numbers.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger("worktime.importers")

FORMAT = "worktime-raw"
VERSION = 1
MAX_DAYS = 400
MAX_ROWS = 500_000


class RawFormatError(ValueError):
    """Raised when a raw export cannot be understood."""


def _require(value, message: str):
    if not value:
        raise RawFormatError(message)
    return value


def _ts(value) -> str:
    text = str(value or "").strip()
    if len(text) == 19 and text[4] == "-" and text[13] == ":":
        return text
    raise RawFormatError(f"时间格式不对（需要 YYYY-MM-DDTHH:MM:SS）: {text!r}")


def load_document(path: str | Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise RawFormatError(f"文件不存在：{path}")
    except ValueError as exc:
        raise RawFormatError(f"不是合法的 JSON：{path}") from exc


def validate_document(doc: dict) -> dict:
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise RawFormatError("不是 WorkTime 原始事件导出（format 应为 worktime-raw）")
    version = int(doc.get("version") or 0)
    if version > VERSION:
        raise RawFormatError(f"导出格式版本 {version} 比本机支持的新，请升级 WorkTime")
    days = doc.get("days")
    if not isinstance(days, dict) or not days:
        raise RawFormatError("没有 days 数据")
    if len(days) > MAX_DAYS:
        raise RawFormatError(f"天数过多（{len(days)}），请分批导入")
    total = 0
    for date, payload in days.items():
        if not isinstance(date, str) or len(date) != 10:
            raise RawFormatError(f"日期格式不对: {date!r}")
        if not isinstance(payload, dict):
            raise RawFormatError(f"{date} 的载荷不是对象")
        activity = payload.get("activity") or []
        focus = payload.get("focus") or []
        if not isinstance(activity, list) or not isinstance(focus, list):
            raise RawFormatError(f"{date} 的 activity/focus 不是数组")
        total += len(activity) + len(focus)
        if total > MAX_ROWS:
            raise RawFormatError("事件过多，请按天分批导入")
        for row in activity:
            if not isinstance(row, dict):
                raise RawFormatError(f"{date} 的 activity 行不是对象")
            _ts(row.get("ts"))
        for row in focus:
            if not isinstance(row, dict):
                raise RawFormatError(f"{date} 的 focus 行不是对象")
            _ts(row.get("ts"))
    return doc


def import_document(store, doc: dict, replace: bool = True,
                    progress=None) -> dict:
    """Insert the export into raw_activity/focus_events. Returns counters."""
    validate_document(doc)
    days = doc["days"]
    imported = {"days": 0, "activity": 0, "focus": 0, "skipped": []}
    for date in sorted(days):
        payload = days[date]
        activity = payload.get("activity") or []
        focus = payload.get("focus") or []
        if not activity and not focus:
            imported["skipped"].append(date)
            continue
        if replace:
            store.delete_raw_day(date)
        raw_rows = [
            (
                _ts(row.get("ts")),
                str(row.get("app") or "")[:120],
                str(row.get("proc") or "")[:200],
                str(row.get("title") or "")[:1024],
                int(row.get("pid") or 0),
                float(row.get("idle_sec") or 0),
                str(row.get("screen") or "active"),
            )
            for row in activity
        ]
        focus_rows = [
            (
                _ts(row.get("ts")),
                str(row.get("app") or "")[:120],
                str(row.get("title") or "")[:512],
                str(row.get("text_preview") or "")[:300],
            )
            for row in focus
        ]
        store.bulk_import(raw=raw_rows or None, focus=focus_rows or None)
        imported["days"] += 1
        imported["activity"] += len(raw_rows)
        imported["focus"] += len(focus_rows)
        if progress:
            progress(date, len(raw_rows), len(focus_rows))
    log.info("imported raw: %s", imported)
    return imported


def import_file(store, path: str | Path, replace: bool = True,
                progress=None) -> dict:
    doc = load_document(path)
    return import_document(store, doc, replace=replace, progress=progress)
