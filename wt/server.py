"""Local-only HTTP ingest for the browser extension.

Binds to 127.0.0.1 and accepts POST /api/event from the extension. A shared
token (config.json) keeps arbitrary web pages from posting to it.
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger("worktime.server")

MAX_BODY = 256 * 1024


class IngestHandler(BaseHTTPRequestHandler):
    server_version = "WorkTimeIngest/0.1"

    # injected by the server factory
    store = None
    cfg = None

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        log.debug("%s - %s", self.address_string(), fmt % args)

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-WT-Token")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._json(204, {})

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in ("/api/health", "/health"):
            self._json(200, {"ok": True, "service": "worktime-ingest"})
        else:
            self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/api/event":
            self._json(404, {"ok": False, "error": "not found"})
            return
        token = self.cfg.get("token") or ""
        if token and self.headers.get("X-WT-Token") != token:
            self._json(403, {"ok": False, "error": "bad token"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            self._json(400, {"ok": False, "error": "bad length"})
            return
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8", "replace"))
        except Exception:
            self._json(400, {"ok": False, "error": "bad json"})
            return

        from .util import domain_of, now_iso

        try:
            if self.store.pause_requested():
                self._json(200, {"ok": True, "stored": False, "reason": "capture paused"})
                return
        except Exception:
            pass

        capture = self.cfg.get("capture", {})
        privacy = self.cfg.get("privacy", {})
        if not any(capture.get(k) for k in
                   ("browser_titles", "browser_urls", "browser_page_text")):
            self._json(200, {"ok": True, "stored": False, "reason": "browser capture disabled"})
            return

        url = str(data.get("url") or "")[:2048]
        incognito = 1 if data.get("incognito") else 0
        if incognito:
            self._json(200, {"ok": True, "stored": False, "reason": "incognito"})
            return
        if not url or url.startswith(("chrome://", "edge://", "about:", "devtools://")):
            self._json(200, {"ok": True, "stored": False, "reason": "internal page"})
            return
        domain = domain_of(url).lower()
        excluded = [str(d).strip().lower() for d in (privacy.get("excluded_domains") or [])
                    if str(d).strip()]
        if domain and any(block in domain for block in excluded):
            self._json(200, {"ok": True, "stored": False, "reason": "excluded domain"})
            return

        stored_url = url if capture.get("browser_urls", True) else ""
        stored_title = (str(data.get("page_title") or "")[:512]
                        if capture.get("browser_titles", True) else "")
        page_text = (str(data.get("visible_text") or "")[:1500]
                     if capture.get("browser_page_text", True) else "")
        selection = (str(data.get("selection") or "")[:500]
                     if capture.get("browser_page_text", True) else "")
        self.store.insert_web(
            ts=now_iso(),
            browser=str(data.get("browser") or "browser")[:32],
            url=stored_url,
            page_title=stored_title,
            visible_text=page_text,
            selection=selection,
            incognito=0,
        )
        self._json(200, {"ok": True, "stored": True})


class _ExclusiveHTTPServer(ThreadingHTTPServer):
    # HTTPServer sets allow_reuse_address = 1, which on Windows lets a second
    # process bind the same port; we want a hard single-instance guard.
    allow_reuse_address = False


class IngestServer:
    def __init__(self, store, cfg: dict):
        self.store = store
        self.cfg = cfg
        handler = type("BoundIngestHandler", (IngestHandler,), {"store": store, "cfg": cfg})
        self.httpd = _ExclusiveHTTPServer(("127.0.0.1", int(cfg["ingest_port"])), handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="ingest", daemon=True)

    def start(self) -> None:
        self.thread.start()
        log.info("ingest listening on http://127.0.0.1:%s", self.cfg["ingest_port"])

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
