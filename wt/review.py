"""Local review UI: a visual, draggable timeline for one day.

Serves a small static single-page app from wt/webui and a JSON API:

  GET  /api/day?date=        segments + aliases
  GET  /api/detail?segment=  raw focus / clipboard / page context for a segment
  POST /api/label            set task/matter (single or bulk) + learn aliases
  POST /api/segment/time     move/resize a segment
  POST /api/segment/split    split a segment at a time
  POST /api/segment/merge    merge adjacent segments
  POST /api/process          re-run the pipeline for a day

Binds to 127.0.0.1 only. Static assets are read from disk so the UI can be
replaced without touching this module.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import re
import threading
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import pipeline
from .config import config_path, data_paths, load_config
from .policy import PRESETS, summarize
from .report import (period_range, render_markdown, render_period_markdown,
                     summarize_period, write_report)
from .store import Store
from .util import domain_of, now_iso, normalize_title, today_str

log = logging.getLogger("worktime.review")
WEBUI = Path(__file__).resolve().parent / "webui"


class _ExclusiveHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False  # Windows: refuse a second review instance


def _iso(value: str, day: str) -> str:
    """Accept HH:MM[:SS] or a full ISO timestamp and return a local ISO string."""
    value = (value or "").strip()
    if len(value) <= 8:
        parts = value.split(":")
        hh, mm = int(parts[0]), int(parts[1])
        ss = int(parts[2]) if len(parts) > 2 else 0
        return datetime.strptime(day, "%Y-%m-%d").replace(
            hour=hh, minute=mm, second=ss
        ).strftime("%Y-%m-%dT%H:%M:%S")
    return value[:19]


class ReviewHandler(BaseHTTPRequestHandler):
    server_version = "WorkTimeReview/0.2"
    store: Store | None = None
    cfg: dict | None = None
    default_date: str = ""

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        log.debug("%s - %s", self.address_string(), fmt % args)

    # -- helpers -------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 256 * 1024:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8", "replace"))
        except Exception:
            return {}

    def _serve_static(self, name: str) -> bool:
        path = (WEBUI / name).resolve()
        if WEBUI.resolve() not in path.parents or not path.is_file():
            return False
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, path.read_bytes(), ctype)
        return True

    # -- GET -----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path in ("/", "/index.html"):
            self._serve_static("index.html")
            return
        if parsed.path in ("/app.js", "/style.css"):
            self._serve_static(parsed.path.lstrip("/"))
            return
        if parsed.path == "/api/day":
            date = (query.get("date") or [self.default_date])[0]
            self._json(200, {
                "date": date,
                "segments": self.store.list_segments(date),
                "aliases": self.store.get_aliases(),
                "dates": self.store.list_dates(31),
                "policy": summarize(self.cfg),
            })
            return
        if parsed.path == "/api/settings":
            self._json(200, self._settings_payload())
            return
        if parsed.path == "/api/detail":
            seg_id = int((query.get("segment") or ["0"])[0])
            self._detail(seg_id)
            return
        if parsed.path == "/api/report":
            date = (query.get("date") or [self.default_date])[0]
            period = (query.get("period") or ["day"])[0]
            if period == "day":
                start = end = date
                segments = self.store.list_segments(date)
                markdown = render_markdown(date, segments, self.cfg)
            else:
                start, end = period_range(date, period)
                segments = self.store.fetch_segments_between(start, end)
                markdown = render_period_markdown(segments, self.cfg, period, start, end)
            summary = summarize_period(segments, self.cfg)
            self._json(200, {
                "date": date, "period": period, "start": start, "end": end,
                "markdown": markdown,
                "stats": {
                    key: summary[key] for key in (
                        "active_s", "days", "avg_s", "coverage", "avg_conf",
                        "by_matter", "by_app", "by_task", "by_day", "by_month",
                    )
                },
            })
            return
        if parsed.path == "/api/aliases":
            self._json(200, {"aliases": self.store.get_aliases()})
            return
        self._json(404, {"ok": False, "error": "not found"})

    # -- POST ----------------------------------------------------------
    def do_POST(self) -> None:  # noqa: N802
        from urllib.parse import urlparse

        path = urlparse(self.path).path
        body = self._read_json()
        try:
            if path == "/api/label":
                self._label(body)
            elif path == "/api/settings":
                self._settings(body)
            elif path == "/api/segment/time":
                self._time(body)
            elif path == "/api/segment/split":
                self._split(body)
            elif path == "/api/segment/merge":
                self._merge(body)
            elif path == "/api/process":
                self._process(body)
            else:
                self._json(404, {"ok": False, "error": "not found"})
        except ValueError as exc:
            self._json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:  # pragma: no cover
            log.exception("review API failed")
            self._json(500, {"ok": False, "error": str(exc)})

    # -- actions -------------------------------------------------------
    def _detail(self, seg_id: int) -> None:
        seg = self.store.get_segment(seg_id)
        if not seg:
            self._json(404, {"ok": False, "error": "segment not found"})
            return
        start = (datetime.strptime(seg["start_ts"], "%Y-%m-%dT%H:%M:%S")
                 - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
        end = (datetime.strptime(seg["end_ts"], "%Y-%m-%dT%H:%M:%S")
               + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
        focus = [
            {"ts": e["ts"], "app": e["app"], "title": e["title"], "text": e["text_preview"]}
            for e in self.store.fetch_focus(start, end)
        ][:80]
        clip = [
            {"ts": e["ts"], "app": e["app"], "title": e["title"],
             "preview": e["preview"], "chars": e["chars"]}
            for e in self.store.fetch_clip(start, end)
        ][:80]
        web = [
            {"ts": e["ts"], "browser": e.get("browser") or "",
             "url": e["url"], "page_title": e["page_title"],
             "visible_text": e["visible_text"], "selection": e["selection"]}
            for e in self.store.fetch_web(start, end)
        ][:40]
        siblings = self.store.list_segments(seg["date"])
        prev_seg = next_seg = None
        for idx, item in enumerate(siblings):
            if item["id"] == seg_id:
                prev_seg = siblings[idx - 1] if idx > 0 else None
                next_seg = siblings[idx + 1] if idx + 1 < len(siblings) else None
                break
        self._json(200, {
            "segment": seg, "focus": focus, "clipboard": clip, "web": web,
            "prev": prev_seg, "next": next_seg,
        })

    def _label(self, body: dict) -> None:
        ids = body.get("ids") or ([body["id"]] if body.get("id") else [])
        ids = [int(i) for i in ids if i]
        has_task = "task" in body
        has_matter = "matter" in body
        task = str(body.get("task") or "").strip()[:120]
        matter = str(body.get("matter") or "").strip()[:120]
        learn = bool(body.get("learn", True))
        if not ids:
            self._json(400, {"ok": False, "error": "ids required"})
            return
        updated = []
        learned = 0
        for seg_id in ids:
            target = self.store.get_segment(seg_id)
            if not target:
                continue
            new_task = task if has_task else (target.get("final_task") or "")
            new_matter = matter if has_matter else (target.get("final_matter") or "")
            self.store.update_segment(seg_id, new_task, new_matter)
            if learn and (task or matter):
                learned += self._learn_aliases(target, task, matter)
            updated.append(self.store.get_segment(seg_id))
        self._json(200, {"ok": True, "segments": updated, "aliases": learned})

    def _learn_aliases(self, target: dict, task: str, matter: str) -> int:
        learned = 0
        day = target.get("date") or self.default_date
        segments = self.store.list_segments(day)
        titles = {normalize_title(target.get("title") or "")}
        for seg in segments:
            if seg.get("auto_task") and seg.get("auto_task") == target.get("auto_task"):
                titles.add(normalize_title(seg.get("title") or ""))
        for title in titles:
            cleaned = title
            for sep in (" - ", " — ", " | "):
                if sep in cleaned:
                    cleaned = cleaned.split(sep)[0].strip()
                    break
            cleaned = re.sub(r"^(re|fw|fwd|回复|转发)\s*[:：]\s*", "", cleaned, flags=re.I)
            if 2 <= len(cleaned) <= 60:
                self.store.add_alias("title", cleaned.lower(), task, matter, now_iso())
                learned += 1
        domain = domain_of(target.get("url") or "").lower()
        if domain:
            self.store.add_alias("domain", domain, task, matter, now_iso())
            learned += 1
        return learned

    def _time(self, body: dict) -> None:
        seg = self.store.get_segment(int(body.get("id") or 0))
        if not seg:
            self._json(404, {"ok": False, "error": "segment not found"})
            return
        start = _iso(body.get("start"), seg["date"])
        end = _iso(body.get("end"), seg["date"])
        updated = self.store.update_segment_time(seg["id"], start, end)
        self._json(200, {"ok": True, "segment": updated})

    def _split(self, body: dict) -> None:
        seg = self.store.get_segment(int(body.get("id") or 0))
        if not seg:
            self._json(404, {"ok": False, "error": "segment not found"})
            return
        ts = _iso(body.get("ts"), seg["date"])
        parts = self.store.split_segment(seg["id"], ts)
        self._json(200, {"ok": True, "segments": parts})

    def _merge(self, body: dict) -> None:
        ids = [int(i) for i in (body.get("ids") or [])]
        merged = self.store.merge_segments(ids)
        if not merged:
            self._json(400, {"ok": False, "error": "need at least two segments"})
            return
        self._json(200, {"ok": True, "segment": merged})

    def _process(self, body: dict) -> None:
        date = str(body.get("date") or self.default_date)
        result = pipeline.process_date(self.store, self.cfg, date, use_llm=True)
        write_report(self.store, self.cfg, date)
        self._json(200, {"ok": True, **result})

    # -- capture policy / permissions ---------------------------------
    def _settings_payload(self) -> dict:
        return {
            "effective": {
                "capture": self.cfg.get("capture", {}),
                "display": self.cfg.get("display", {}),
                "privacy": self.cfg.get("privacy", {}),
            },
            "policy": summarize(self.cfg),
            "presets": (self.cfg.get("_policy") or {}).get(
                "presets", ["strict", "metadata", "standard", "full"]),
            "config_path": self.cfg.get("_config_path"),
        }

    def _settings(self, body: dict) -> None:
        policy = self.cfg.get("policy") or {}
        if policy.get("locked"):
            self._json(403, {"ok": False,
                             "error": "采集策略已被管理员锁定（policy.locked = true）"})
            return
        path = config_path()
        try:
            if path.is_file():
                disk = json.loads(path.read_text(encoding="utf-8-sig"))
            else:
                disk = {"token": self.cfg.get("token", "")}
        except Exception:
            disk = {"token": self.cfg.get("token", "")}
        preset = body.get("preset")
        sections_given = any(k in body for k in ("capture", "display", "privacy"))
        if preset:
            disk.setdefault("policy", {})["preset"] = str(preset)
            if not sections_given:
                # Preset-only: drop explicit overrides for keys the preset owns,
                # so switching presets really resets the capture scope.
                for section in ("capture", "display", "privacy"):
                    owned = set((PRESETS.get(str(preset)) or {}).get(section, {}).keys())
                    disk[section] = {
                        k: v for k, v in (disk.get(section) or {}).items()
                        if k not in owned
                    }
        for section in ("capture", "display", "privacy"):
            incoming = body.get(section)
            if isinstance(incoming, dict):
                target = disk.setdefault(section, {})
                for key, value in incoming.items():
                    target[key] = value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(disk, ensure_ascii=False, indent=2), encoding="utf-8")

        fresh = load_config()
        self.cfg.clear()
        self.cfg.update(fresh)
        self._json(200, {"ok": True, "restart_required": True, **self._settings_payload()})


class ReviewServer:
    def __init__(self, cfg: dict, date: str):
        self.cfg = cfg
        paths = data_paths(cfg)
        self.store = Store(paths["db"])
        if not date:
            date = self.store.latest_segment_date() or today_str()
        handler = type("BoundReviewHandler", (ReviewHandler,), {
            "store": self.store, "cfg": cfg, "default_date": date,
        })
        self.httpd = _ExclusiveHTTPServer(("127.0.0.1", int(cfg["review_port"])), handler)
        self.httpd.daemon_threads = True

    def run(self) -> None:
        url = f"http://127.0.0.1:{self.cfg['review_port']}/"
        log.info("review UI: %s", url)
        print(f"复核页已启动：{url}")
        print("（如果浏览器没有自动打开，请手动访问上面的地址；Ctrl+C 退出）")
        if self.cfg.get("review_open_browser", True):
            def _open() -> None:
                try:
                    webbrowser.open(url)
                except Exception:
                    pass

            threading.Timer(1.0, _open).start()
        try:
            self.httpd.serve_forever()
        except KeyboardInterrupt:
            pass


def serve(cfg: dict | None = None, date: str | None = None) -> None:
    cfg = cfg or load_config()
    ReviewServer(cfg, date or "").run()
