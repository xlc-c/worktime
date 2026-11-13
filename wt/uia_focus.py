"""Optional UI Automation reader for the focused control's text.

This is what lets us know what someone is typing/reading inside Excel cells,
Outlook mail bodies or Lync conversations. It depends on the optional
`uiautomation` package and silently degrades when unavailable.

We deliberately do *not* install keyboard hooks: reading the focused
control's value is both more meaningful (works with IME input) and much less
likely to be flagged as a keylogger.

Safety rules enforced here (independent of the capture preset):

* password / protected controls are never read (``IsPassword`` property);
* excluded apps (banking, password managers, ...) are skipped;
* the stored text is truncated to ``uia_max_chars`` (default 300).
"""

from __future__ import annotations

import threading
import time

from . import winapi
from .util import is_probably_sensitive

try:  # optional dependency
    import uiautomation as _auto  # type: ignore
except Exception:  # pragma: no cover - optional
    _auto = None

if _auto is not None:
    try:
        _auto.SetGlobalSearchTimeout(2.0)
    except Exception:
        pass


def available() -> bool:
    return _auto is not None


def _clean(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").strip()
    text = " ".join(text.split())
    return text


def _is_password_control(control) -> bool:
    """UIA marks password fields with IsPassword; never read those."""
    try:
        if bool(getattr(control, "IsPassword", False)):
            return True
    except Exception:
        pass
    # Some providers expose the pattern flag instead of the property.
    try:
        value_pattern = control.GetValuePattern()
        if value_pattern is not None and bool(getattr(value_pattern, "IsPassword", False)):
            return True
    except Exception:
        pass
    return False


def read_focused_text(limit: int = 300) -> str:
    """Read the focused control's text, or "" when it is not safe to read."""
    if _auto is None:
        return ""
    try:
        control = _auto.GetFocusedControl()
    except Exception:
        return ""
    if control is None:
        return ""
    if _is_password_control(control):
        return ""
    text = ""
    # Prefer the value (edit boxes, spreadsheet cells, mail body).
    try:
        value_pattern = control.GetValuePattern()
        if value_pattern is not None:
            text = _clean(value_pattern.Value)
    except Exception:
        text = ""
    # Text pattern for document-like controls.
    if not text:
        try:
            text_pattern = control.GetTextPattern()
            if text_pattern is not None:
                text = _clean(text_pattern.DocumentRange.GetText(500))
        except Exception:
            pass
    if not text:
        try:
            text = _clean(control.Name)
        except Exception:
            text = ""
    if not text:
        return ""
    # Never store obvious secrets verbatim, even when focused in a whitelisted app.
    if is_probably_sensitive(text):
        return ""
    return text[:max(20, int(limit))]


class FocusSampler(threading.Thread):
    """Background sampler that stores focused-text changes."""

    def __init__(self, store, cfg: dict, stop_event: threading.Event):
        super().__init__(name="focus-sampler", daemon=True)
        self.store = store
        self.cfg = cfg
        self.stop_event = stop_event
        self.interval = float(cfg.get("uia_interval_s", 6.0))
        self.limit = int(cfg.get("uia_max_chars", 300))
        privacy = cfg.get("privacy", {})
        self.apps = {a.lower() for a in cfg.get("uia_apps", [])}
        self.excluded = {
            str(a).strip().lower()
            for a in (privacy.get("excluded_apps") or [])
            if str(a).strip()
        }
        self._last = ""
        self._last_key = ""

    def _excluded(self, fg: dict) -> bool:
        if not self.excluded:
            return False
        app = (fg.get("app") or "").lower()
        proc = (fg.get("proc") or "").lower()
        return app in self.excluded or proc in self.excluded

    def sample_once(self, fg: dict) -> bool:
        """Read once; returns True when a new focus row was stored."""
        from .util import now_iso

        app_key = (fg.get("app") or "").lower()
        if not any(app_key.startswith(a) or a in app_key for a in self.apps):
            return False
        if self._excluded(fg):
            return False
        try:
            if self.store.pause_requested():
                return False
        except Exception:
            pass
        text = read_focused_text(self.limit)
        if not text:
            return False
        if text == self._last and fg["title"] == self._last_key:
            return False
        self._last = text
        self._last_key = fg["title"]
        self.store.insert_focus(now_iso(), fg["app"], fg["title"], text)
        return True

    def run(self) -> None:  # pragma: no cover - exercised on a live desktop
        while not self.stop_event.is_set():
            try:
                if _auto is not None:
                    self.sample_once(winapi.get_foreground())
            except Exception:
                pass
            self.stop_event.wait(self.interval)
