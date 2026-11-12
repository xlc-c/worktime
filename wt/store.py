"""SQLite persistence for raw capture and processed timeline."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    app TEXT,
    proc TEXT,
    title TEXT,
    pid INTEGER,
    idle_sec REAL DEFAULT 0,
    screen TEXT DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_raw_ts ON raw_activity(ts);

CREATE TABLE IF NOT EXISTS web_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    browser TEXT,
    url TEXT,
    page_title TEXT,
    visible_text TEXT,
    selection TEXT,
    incognito INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_web_ts ON web_events(ts);

CREATE TABLE IF NOT EXISTS clipboard_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    text_hash TEXT,
    preview TEXT,
    app TEXT,
    title TEXT,
    chars INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_clip_ts ON clipboard_events(ts);

CREATE TABLE IF NOT EXISTS focus_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    app TEXT,
    title TEXT,
    text_preview TEXT
);
CREATE INDEX IF NOT EXISTS idx_focus_ts ON focus_events(ts);

CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    start_ts TEXT NOT NULL,
    end_ts TEXT NOT NULL,
    duration_s REAL,
    kind TEXT DEFAULT 'work',
    app TEXT,
    title TEXT,
    url TEXT,
    page_title TEXT,
    focused_text TEXT,
    clipboard_text TEXT,
    link_id TEXT,
    auto_task TEXT,
    auto_matter TEXT,
    confidence REAL,
    final_task TEXT,
    final_matter TEXT,
    evidence TEXT
);
CREATE INDEX IF NOT EXISTS idx_seg_date ON segments(date);

CREATE TABLE IF NOT EXISTS aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    pattern TEXT NOT NULL,
    task TEXT,
    matter TEXT,
    created_ts TEXT,
    UNIQUE(kind, pattern)
);

CREATE TABLE IF NOT EXISTS processed_days (
    date TEXT PRIMARY KEY,
    processed_at TEXT,
    version INTEGER DEFAULT 1
);
"""


class Store:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            try:
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=NORMAL")
            except Exception:
                pass
            self._conn.commit()

    # -- low level -----------------------------------------------------
    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params).fetchall())

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- raw writes ----------------------------------------------------
    def insert_raw(self, ts: str, app: str, proc: str, title: str, pid: int,
                   idle_sec: float, screen: str = "active") -> None:
        self._exec(
            "INSERT INTO raw_activity(ts, app, proc, title, pid, idle_sec, screen)"
            " VALUES(?,?,?,?,?,?,?)",
            (ts, app, proc, title, pid, idle_sec, screen),
        )

    def insert_web(self, ts: str, browser: str, url: str, page_title: str,
                   visible_text: str, selection: str, incognito: int = 0) -> None:
        self._exec(
            "INSERT INTO web_events(ts, browser, url, page_title, visible_text,"
            " selection, incognito) VALUES(?,?,?,?,?,?,?)",
            (ts, browser, url, page_title, visible_text, selection, incognito),
        )

    def insert_clip(self, ts: str, text_hash: str, preview: str, app: str,
                    title: str, chars: int) -> None:
        self._exec(
            "INSERT INTO clipboard_events(ts, text_hash, preview, app, title, chars)"
            " VALUES(?,?,?,?,?,?)",
            (ts, text_hash, preview, app, title, chars),
        )

    def insert_focus(self, ts: str, app: str, title: str, text_preview: str) -> None:
        self._exec(
            "INSERT INTO focus_events(ts, app, title, text_preview) VALUES(?,?,?,?)",
            (ts, app, title, text_preview),
        )

    def bulk_import(self, raw: list[tuple] | None = None,
                    web: list[tuple] | None = None,
                    clip: list[tuple] | None = None,
                    focus: list[tuple] | None = None) -> None:
        """Single-transaction bulk insert (used by simulate/importers)."""
        with self._lock:
            if raw:
                self._conn.executemany(
                    "INSERT INTO raw_activity(ts, app, proc, title, pid, idle_sec, screen)"
                    " VALUES(?,?,?,?,?,?,?)", raw)
            if web:
                self._conn.executemany(
                    "INSERT INTO web_events(ts, browser, url, page_title, visible_text,"
                    " selection, incognito) VALUES(?,?,?,?,?,?,?)", web)
            if clip:
                self._conn.executemany(
                    "INSERT INTO clipboard_events(ts, text_hash, preview, app, title, chars)"
                    " VALUES(?,?,?,?,?,?)", clip)
            if focus:
                self._conn.executemany(
                    "INSERT INTO focus_events(ts, app, title, text_preview) VALUES(?,?,?,?)",
                    focus)
            self._conn.commit()

    # -- range reads ---------------------------------------------------
    def fetch_raw(self, start: str, end: str) -> list[dict]:
        rows = self._query(
            "SELECT * FROM raw_activity WHERE ts >= ? AND ts < ? ORDER BY ts",
            (start, end),
        )
        return [dict(r) for r in rows]

    def fetch_web(self, start: str, end: str) -> list[dict]:
        rows = self._query(
            "SELECT * FROM web_events WHERE ts >= ? AND ts < ? ORDER BY ts",
            (start, end),
        )
        return [dict(r) for r in rows]

    def fetch_clip(self, start: str, end: str) -> list[dict]:
        rows = self._query(
            "SELECT * FROM clipboard_events WHERE ts >= ? AND ts < ? ORDER BY ts",
            (start, end),
        )
        return [dict(r) for r in rows]

    def fetch_focus(self, start: str, end: str) -> list[dict]:
        rows = self._query(
            "SELECT * FROM focus_events WHERE ts >= ? AND ts < ? ORDER BY ts",
            (start, end),
        )
        return [dict(r) for r in rows]

    # -- processed segments -------------------------------------------
    def replace_segments(self, date: str, segments: list[dict]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM segments WHERE date = ?", (date,))
            self._conn.executemany(
                """INSERT INTO segments(
                    date, start_ts, end_ts, duration_s, kind, app, title, url,
                    page_title, focused_text, clipboard_text, link_id,
                    auto_task, auto_matter, confidence, final_task, final_matter,
                    evidence)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        s.get("date", date),
                        s["start_ts"],
                        s["end_ts"],
                        s["duration_s"],
                        s.get("kind", "work"),
                        s.get("app", ""),
                        s.get("title", ""),
                        s.get("url", ""),
                        s.get("page_title", ""),
                        s.get("focused_text", ""),
                        s.get("clipboard_text", ""),
                        s.get("link_id", ""),
                        s.get("auto_task", ""),
                        s.get("auto_matter", ""),
                        s.get("confidence", 0.0),
                        s.get("final_task", ""),
                        s.get("final_matter", ""),
                        s.get("evidence", ""),
                    )
                    for s in segments
                ],
            )
            self._conn.commit()

    def list_segments(self, date: str) -> list[dict]:
        rows = self._query(
            "SELECT * FROM segments WHERE date = ? ORDER BY start_ts", (date,)
        )
        return [dict(r) for r in rows]

    def fetch_segments_between(self, start_date: str, end_date: str) -> list[dict]:
        rows = self._query(
            "SELECT * FROM segments WHERE date >= ? AND date <= ?"
            " ORDER BY date, start_ts",
            (start_date, end_date),
        )
        return [dict(r) for r in rows]

    def get_segment(self, seg_id: int) -> dict | None:
        rows = self._query("SELECT * FROM segments WHERE id = ?", (seg_id,))
        return dict(rows[0]) if rows else None

    # -- manual timeline edits ----------------------------------------
    def update_segment_time(self, seg_id: int, start_ts: str, end_ts: str) -> dict | None:
        from .util import ts_to_dt

        seg = self.get_segment(seg_id)
        if not seg:
            return None
        duration = (ts_to_dt(end_ts) - ts_to_dt(start_ts)).total_seconds()
        if duration < 60:
            raise ValueError("segment must be at least 1 minute")
        self._exec(
            "UPDATE segments SET start_ts = ?, end_ts = ?, duration_s = ? WHERE id = ?",
            (start_ts, end_ts, duration, seg_id),
        )
        return self.get_segment(seg_id)

    def split_segment(self, seg_id: int, split_ts: str) -> list[dict]:
        from .util import ts_to_dt

        seg = self.get_segment(seg_id)
        if not seg:
            return []
        start, end = ts_to_dt(seg["start_ts"]), ts_to_dt(seg["end_ts"])
        middle = ts_to_dt(split_ts)
        if not (start < middle < end):
            raise ValueError("split time must be inside the segment")
        self._exec(
            "UPDATE segments SET end_ts = ?, duration_s = ? WHERE id = ?",
            (split_ts, (middle - start).total_seconds(), seg_id),
        )
        clone = dict(seg)
        clone.pop("id", None)
        clone["start_ts"] = split_ts
        clone["end_ts"] = seg["end_ts"]
        clone["duration_s"] = (end - middle).total_seconds()
        clone["evidence"] = seg.get("evidence") or ""
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO segments(
                    date, start_ts, end_ts, duration_s, kind, app, title, url,
                    page_title, focused_text, clipboard_text, link_id,
                    auto_task, auto_matter, confidence, final_task, final_matter,
                    evidence)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    clone["date"], clone["start_ts"], clone["end_ts"],
                    clone["duration_s"], clone.get("kind", "work"),
                    clone.get("app", ""), clone.get("title", ""),
                    clone.get("url", ""), clone.get("page_title", ""),
                    clone.get("focused_text", ""), clone.get("clipboard_text", ""),
                    clone.get("link_id", ""), clone.get("auto_task", ""),
                    clone.get("auto_matter", ""), clone.get("confidence", 0.0),
                    clone.get("final_task", ""), clone.get("final_matter", ""),
                    clone.get("evidence", ""),
                ),
            )
            clone_id = cur.lastrowid
            self._conn.commit()
        return [self.get_segment(seg_id), self.get_segment(clone_id)]

    def merge_segments(self, ids: list[int]) -> dict | None:
        from .util import ts_to_dt

        segments = [s for s in (self.get_segment(i) for i in ids) if s]
        if len(segments) < 2:
            return segments[0] if segments else None
        segments.sort(key=lambda s: s["start_ts"])
        first = segments[0]
        start = first["start_ts"]
        end = max(s["end_ts"] for s in segments)
        primary = max(segments, key=lambda s: s.get("duration_s") or 0)
        task = next((s["final_task"] for s in segments if s.get("final_task")), "")
        matter = next((s["final_matter"] for s in segments if s.get("final_matter")), "")
        evidence = " | ".join(s.get("evidence") or "" for s in segments if s.get("evidence"))
        self._exec(
            "UPDATE segments SET start_ts = ?, end_ts = ?, duration_s = ?, app = ?,"
            " title = ?, url = ?, page_title = ?, final_task = ?, final_matter = ?,"
            " evidence = ? WHERE id = ?",
            (
                start, end,
                (ts_to_dt(end) - ts_to_dt(start)).total_seconds(),
                primary.get("app", ""), primary.get("title", ""),
                primary.get("url", ""), primary.get("page_title", ""),
                task, matter, evidence, first["id"],
            ),
        )
        keep = first["id"]
        for seg in segments[1:]:
            self._exec("DELETE FROM segments WHERE id = ?", (seg["id"],))
        return self.get_segment(keep)

    def update_segment(self, seg_id: int, task: str, matter: str) -> dict | None:
        self._exec(
            "UPDATE segments SET final_task = ?, final_matter = ? WHERE id = ?",
            (task, matter, seg_id),
        )
        rows = self._query("SELECT * FROM segments WHERE id = ?", (seg_id,))
        return dict(rows[0]) if rows else None

    # -- aliases / metadata -------------------------------------------
    def add_alias(self, kind: str, pattern: str, task: str, matter: str,
                  created_ts: str) -> None:
        self._exec(
            "INSERT INTO aliases(kind, pattern, task, matter, created_ts)"
            " VALUES(?,?,?,?,?)"
            " ON CONFLICT(kind, pattern) DO UPDATE SET"
            " task = excluded.task, matter = excluded.matter,"
            " created_ts = excluded.created_ts",
            (kind, pattern, task, matter, created_ts),
        )

    def get_aliases(self) -> list[dict]:
        return [dict(r) for r in self._query("SELECT * FROM aliases ORDER BY id")]

    def delete_alias(self, alias_id: int) -> None:
        self._exec("DELETE FROM aliases WHERE id = ?", (alias_id,))

    def mark_processed(self, date: str, processed_at: str) -> None:
        self._exec(
            "INSERT INTO processed_days(date, processed_at) VALUES(?,?)"
            " ON CONFLICT(date) DO UPDATE SET processed_at = excluded.processed_at",
            (date, processed_at),
        )

    def delete_day(self, date: str) -> None:
        """Remove captured data and segments for one day (used by simulate/reset)."""
        start, end = date + "T00:00:00", date + "T23:59:59"
        with self._lock:
            for table in ("raw_activity", "web_events", "clipboard_events", "focus_events"):
                self._conn.execute(
                    f"DELETE FROM {table} WHERE ts >= ? AND ts <= ?", (start, end)
                )
            self._conn.execute("DELETE FROM segments WHERE date = ?", (date,))
            self._conn.execute("DELETE FROM processed_days WHERE date = ?", (date,))
            self._conn.commit()

    def processed(self, date: str) -> bool:
        return bool(self._query("SELECT 1 FROM processed_days WHERE date = ?", (date,)))

    def list_dates(self, limit: int = 30) -> list[dict]:
        rows = self._query(
            "SELECT date, COUNT(*) AS n, SUM(duration_s) AS seconds FROM segments"
            " GROUP BY date ORDER BY date DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]

    def latest_segment_date(self) -> str:
        rows = self._query("SELECT date FROM segments ORDER BY date DESC LIMIT 1")
        return rows[0]["date"] if rows else ""

    # -- housekeeping --------------------------------------------------
    def prune(self, retention_days: int, raw_clipboard_days: int) -> dict:
        from datetime import datetime, timedelta

        cutoff = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%dT%H:%M:%S")
        clip_cutoff = (datetime.now() - timedelta(days=raw_clipboard_days)).strftime("%Y-%m-%dT%H:%M:%S")
        deleted = {}
        with self._lock:
            for table in ("raw_activity", "web_events", "focus_events", "segments"):
                cur = self._conn.execute(f"DELETE FROM {table} WHERE ts < ?" if table != "segments" else f"DELETE FROM {table} WHERE start_ts < ?", (cutoff,))
                deleted[table] = cur.rowcount
            cur = self._conn.execute(
                "DELETE FROM clipboard_events WHERE ts < ?", (clip_cutoff,)
            )
            deleted["clipboard_events"] = cur.rowcount
            self._conn.commit()
        return deleted

    def stats(self) -> dict:
        counts = {}
        for table in ("raw_activity", "web_events", "clipboard_events",
                      "focus_events", "segments", "aliases"):
            counts[table] = self._query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]
        return counts
