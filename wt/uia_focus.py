"""Optional UI Automation reader for the focused control's text.

This is what lets us know what someone is typing/reading inside Excel cells,
Outlook mail bodies or Lync conversations. It depends on the optional
`uiautomation` package and silently degrades when unavailable.

We deliberately do *not* install keyboard hooks: reading the focused
control's value is both more meaningful (works with IME input) and much less
likely to be flagged as a keylogger.
"""

from __future__ import annotations

import threading
import time

from . import winapi

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


def _read_focused() -> str:
    if _auto is None:
        return ""
    try:
        control = _auto.GetFocusedControl()
        if control is None:
            return ""
        # Prefer the value (edit boxes, spreadsheet cells, mail body).
        try:
            value_pattern = control.GetValuePattern()
            if value_pattern is not None:
                value = _clean(value_pattern.Value)
                if value:
                    return value
        except Exception:
            pass
        # Text pattern for document-like controls.
        try:
            text_pattern = control.GetTextPattern()
            if text_pattern is not None:
                value = _clean(text_pattern.DocumentRange.GetText(500))
                if value:
                    return value
        except Exception:
            pass
        name = _clean(control.Name)
        return name
    except Exception:
        return ""


class FocusSampler(threading.Thread):
    """Background sampler that stores focused-text changes."""

    def __init__(self, store, cfg: dict, stop_event: threading.Event):
        super().__init__(name="focus-sampler", daemon=True)
        self.store = store
        self.cfg = cfg
        self.stop_event = stop_event
        self.interval = float(cfg.get("uia_interval_s", 6.0))
        self.apps = {a.lower() for a in cfg.get("uia_apps", [])}
        self._last = ""
        self._last_key = ""

    def run(self) -> None:  # pragma: no cover - exercised on a live desktop
        from .util import now_iso

        while not self.stop_event.is_set():
            try:
                if _auto is not None:
                    fg = winapi.get_foreground()
                    app_key = (fg["app"] or "").lower()
                    if any(app_key.startswith(a) or a in app_key for a in self.apps):
                        text = _read_focused()[:300]
                        if text and (text != self._last or fg["title"] != self._last_key):
                            self._last = text
                            self._last_key = fg["title"]
                            self.store.insert_focus(
                                now_iso(), fg["app"], fg["title"], text
                            )
            except Exception:
                pass
            self.stop_event.wait(self.interval)
