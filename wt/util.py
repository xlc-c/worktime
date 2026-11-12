"""Small shared helpers: time formatting, hashing, title normalization."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta

ISO_FMT = "%Y-%m-%dT%H:%M:%S"


def now_iso() -> str:
    return datetime.now().strftime(ISO_FMT)


def ts_to_dt(ts: str) -> datetime:
    return datetime.strptime(ts[:19], ISO_FMT)


def dt_to_ts(dt: datetime) -> str:
    return dt.strftime(ISO_FMT)


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def day_bounds(date_str: str) -> tuple[str, str]:
    """Return [start, end) ISO timestamps for a local calendar date."""
    start = datetime.strptime(date_str, "%Y-%m-%d")
    end = start + timedelta(days=1)
    return start.strftime(ISO_FMT), end.strftime(ISO_FMT)


def shift_date(date_str: str, days: int) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=days)
    return d.strftime("%Y-%m-%d")


def fmt_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def fmt_clock(ts: str) -> str:
    return ts[11:16]


_BROWSER_SUFFIXES = (
    " - Google Chrome",
    " - Microsoft\u200b Edge",
    " - Microsoft Edge",
    " - Mozilla Firefox",
    " - Brave",
    " - Vivaldi",
    " - Opera",
    " - Chromium",
)


def normalize_title(title: str) -> str:
    title = (title or "").strip()
    for suffix in _BROWSER_SUFFIXES:
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
    title = re.sub(r"\s+", " ", title)
    return title


def hash_text(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8", "ignore")).hexdigest()


def clip_preview(text: str, limit: int) -> str:
    text = (text or "").replace("\r\n", "\n").strip()
    text = re.sub(r"[ \t]+", " ", text)
    if len(text) > limit:
        return text[:limit] + "\u2026"
    return text


def domain_of(url: str) -> str:
    if not url:
        return ""
    m = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://([^/?#]+)", url)
    if not m:
        return ""
    host = m.group(1).lower()
    if "@" in host:
        host = host.rsplit("@", 1)[1]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


def is_probably_sensitive(text: str) -> bool:
    """Cheap heuristics so secrets do not get stored verbatim."""
    if not text:
        return False
    # private key blocks
    if "-----BEGIN " in text and "PRIVATE KEY-----" in text:
        return True
    # password-ish assignments
    if re.search(r"(?i)(password|passwd|pwd|secret|token|api[_-]?key)\s*[:=]\s*\S{6,}", text):
        return True
    return False
