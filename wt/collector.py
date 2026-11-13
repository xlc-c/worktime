"""Foreground activity collector.

Samples the foreground window, keyboard/mouse idleness and clipboard, and
accepts page context from the browser extension. Runs until Ctrl+C or the
stop event is set.

Design notes
------------
* No keyboard hooks, no screenshots by default: low AV risk, low CPU.
* Rows are written on change plus a periodic heartbeat, so a day is a few
  thousand rows instead of tens of thousands.
* Everything is local: SQLite + 127.0.0.1 HTTP only.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import signal
import sys
import threading
import time

from . import winapi
from .config import data_paths, load_config
from .server import IngestServer
from .store import Store
from .uia_focus import FocusSampler
from .util import (clip_preview_safe, hash_text,
                   is_probably_sensitive, now_iso)

log = logging.getLogger("worktime.collector")


def setup_logging(cfg: dict) -> None:
    paths = data_paths(cfg)
    logfile = paths["logs"] / "collector.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(
        logfile, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.handlers = [fh, sh]


class Collector:
    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or load_config()
        self.paths = data_paths(self.cfg)
        self.store = Store(self.paths["db"])
        self.stop_event = threading.Event()
        try:
            self.ingest = IngestServer(self.store, self.cfg)
            self._port_error: Exception | None = None
        except OSError as exc:
            # Another collector instance already owns the port.
            self.ingest = None
            self._port_error = exc
        self.focus = FocusSampler(self.store, self.cfg, self.stop_event)
        self._last_key: tuple[str, str] | None = None
        self._last_write = 0.0
        self._last_clip_hash = ""
        self._clip_initialized = False
        self._away = False
        self._samples = 0
        self._clip_events = 0
        self.capture = self.cfg.get("capture", {})
        self.excluded_apps = {
            str(a).strip().lower()
            for a in (self.cfg.get("privacy", {}).get("excluded_apps") or [])
            if str(a).strip()
        }

    def _is_excluded(self, fg: dict) -> bool:
        if not self.excluded_apps:
            return False
        app = (fg.get("app") or "").lower()
        proc = (fg.get("proc") or "").lower()
        return app in self.excluded_apps or proc in self.excluded_apps

    # ------------------------------------------------------------------
    def _clipboard_capture(self, fg: dict) -> None:
        if not self.capture.get("clipboard"):
            return
        preview_chars = int(self.capture.get("clipboard_preview_chars") or 0)
        if preview_chars <= 0:
            return
        text = winapi.get_clipboard_text()
        if not text:
            return
        digest = hash_text(text)
        if not self._clip_initialized:
            # Whatever was already in the clipboard at startup is not a new copy
            # event; ignore it (and never persist stale/secret content).
            self._clip_initialized = True
            self._last_clip_hash = digest
            return
        if digest == self._last_clip_hash:
            return
        self._last_clip_hash = digest
        if len(text.strip()) < 2:
            return
        if is_probably_sensitive(text):
            log.info("clipboard event skipped (looks sensitive)")
            return
        exclude = {a.lower() for a in self.cfg.get("clipboard_exclude_apps", [])}
        exclude |= self.excluded_apps
        if (fg["app"] or "").lower() in exclude or (fg["proc"] or "") in exclude:
            log.info("clipboard event skipped (excluded app %s)", fg["app"])
            return
        preview, redacted = clip_preview_safe(text, preview_chars)
        if redacted:
            # Random-looking business data (card numbers, ids, tokens): keep the
            # fact that something was copied, never the text itself.
            log.info("clipboard preview redacted (high-entropy content)")
        self.store.insert_clip(
            now_iso(), digest, preview, fg["app"], fg["title"][:512], len(text)
        )
        self._clip_events += 1

    def _write_raw(self, fg: dict, idle: float) -> None:
        title = fg["title"] if self.capture.get("window_titles", True) else ""
        self.store.insert_raw(
            now_iso(), fg["app"], fg["proc"], title[:1024], fg["pid"],
            idle, "active",
        )
        self._last_write = time.time()
        self._last_key = (fg["app"], title)
        self._samples += 1

    # ------------------------------------------------------------------
    def run(self) -> None:
        setup_logging(self.cfg)
        if self._port_error is not None:
            log.error("ingest port %s unavailable (%s); another collector is probably running",
                      self.cfg["ingest_port"], self._port_error)
            if sys.stdout is not None:
                print(f"已有采集进程在运行（端口 {self.cfg['ingest_port']} 被占用），本次不重复启动。")
            self.store.close()
            return
        self.store.prune(
            int(self.cfg["privacy"]["retention_days"]),
            int(self.cfg["privacy"]["store_raw_clipboard_days"]),
        )
        self.ingest.start()
        if self.capture.get("focused_text", True):
            self.focus.start()
        else:
            log.info("focused-text capture disabled by policy")

        def _stop(signum, frame):  # noqa: ARG001
            log.info("stopping (signal %s)", signum)
            self.stop_event.set()

        try:
            signal.signal(signal.SIGINT, _stop)
            signal.signal(signal.SIGTERM, _stop)
        except Exception:
            pass

        interval = float(self.cfg.get("sample_interval_s", 2.0))
        heartbeat = float(self.cfg.get("heartbeat_s", 20.0))
        idle_threshold = float(self.cfg.get("idle_threshold_s", 120))
        clip_interval = float(self.cfg.get("clipboard_poll_s", 1.0))
        next_clip = 0.0
        last_stats = time.time()
        last_beat = 0.0
        paused = False
        self.store.set_meta("collector.pid", str(os.getpid()))
        self.store.set_meta("collector.started_at", now_iso())
        self.store.set_meta("collector.paused", "0")
        log.info("collector started; data dir=%s; policy=%s", self.paths["data"],
                 (self.cfg.get("policy") or {}).get("preset", "standard"))
        if sys.stdout is not None:  # pythonw.exe has no console
            print("采集已启动（后台运行，本来就没有窗口，这是正常的）。")
            print(f"采集范围：{self.cfg.get('policy', {}).get('preset', 'standard')}")
            print(f"要看界面/时间线：双击 review.bat，或浏览器访问 "
                  f"http://127.0.0.1:{self.cfg['review_port']}/")
            print(f"数据目录：{self.paths['data']}   （Ctrl+C 停止采集）")

        while not self.stop_event.is_set():
            loop_start = time.time()
            try:
                fg = winapi.get_foreground()
                idle = winapi.get_idle_seconds()

                # Pause switch from the review UI / tray icon (no IPC, one row in meta).
                want_pause = self.store.pause_requested()
                if want_pause != paused:
                    paused = want_pause
                    log.info("capture %s by user", "paused" if paused else "resumed")
                    self._last_key = None

                if paused:
                    self._last_key = None
                elif self._is_excluded(fg):
                    # Excluded app (e.g. banking, password manager): do not record.
                    self._last_key = None
                elif idle >= idle_threshold:
                    if not self._away:
                        self._away = True
                        self._last_key = None
                        log.info("user away (idle %.0fs)", idle)
                else:
                    if self._away:
                        self._away = False
                        self._last_key = None  # force a fresh row after returning
                    key = (fg["app"], fg["title"])
                    if key != self._last_key or (loop_start - self._last_write) >= heartbeat:
                        self._write_raw(fg, idle)

                if loop_start >= next_clip:
                    if not paused:
                        self._clipboard_capture(fg)
                    next_clip = loop_start + clip_interval

                if loop_start - last_beat >= 5:
                    last_beat = loop_start
                    self.store.set_meta("collector.last_sample", now_iso())

                if time.time() - last_stats >= 300:
                    last_stats = time.time()
                    log.info(
                        "stats: raw=%d clip=%d away=%s",
                        self._samples, self._clip_events, self._away,
                    )
            except Exception:  # pragma: no cover - keep the daemon alive
                log.exception("sample failed")

            elapsed = time.time() - loop_start
            self.stop_event.wait(max(0.05, interval - elapsed))

        log.info("shutting down")
        self.stop_event.set()
        try:
            self.store.set_meta("collector.pid", "")
            self.store.set_meta("collector.last_sample", "")
        except Exception:
            pass
        if self.ingest is not None:
            self.ingest.stop()
        self.store.close()


def main() -> None:
    Collector().run()


if __name__ == "__main__":
    main()
