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
    # JWT / bearer tokens
    if re.search(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b", text):
        return True
    # AWS access key ids / long hex or base64 blobs with no spaces
    if re.search(r"\bAKIA[0-9A-Z]{16}\b", text):
        return True
    for token in re.findall(r"[A-Za-z0-9+/=_-]{32,}", text):
        if _entropy(token) >= 4.2 and _classes(token) >= 3:
            return True
    # payment card numbers (Luhn), with or without separators
    for candidate in re.findall(r"\d(?:[ -]?\d){12,18}", text):
        digits = re.sub(r"\D", "", candidate)
        if 13 <= len(digits) <= 19 and _luhn(digits):
            return True
    # 18-digit national id numbers
    if re.search(r"(?<!\d)\d{17}[\dXx](?!\d)", text):
        return True
    return False


def _entropy(token: str) -> float:
    """Shannon entropy per character of a single token."""
    import math

    if not token:
        return 0.0
    counts: dict[str, int] = {}
    for ch in token:
        counts[ch] = counts.get(ch, 0) + 1
    total = len(token)
    return -sum((n / total) * math.log2(n / total) for n in counts.values())


def _classes(token: str) -> int:
    return sum((
        any(c.islower() for c in token),
        any(c.isupper() for c in token),
        any(c.isdigit() for c in token),
        any(not c.isalnum() for c in token),
    ))


def _luhn(digits: str) -> bool:
    total = 0
    for idx, ch in enumerate(reversed(digits)):
        n = int(ch)
        if idx % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def is_high_entropy(text: str) -> bool:
    """Looks like a random token/secret but is not matched by a known pattern.

    Such content is still recorded as a copy event (hash + length), but the
    preview is dropped so the text itself never reaches the database.
    """
    if not text:
        return False
    stripped = text.strip()
    if not stripped or re.search(r"\s", stripped):
        return False
    if len(stripped) < 20:
        return False
    return _entropy(stripped) >= 4.0 and _classes(stripped) >= 2


def clip_preview_safe(text: str, limit: int) -> tuple[str, bool]:
    """Return (preview, redacted). Sensitive/random content is not stored."""
    if is_probably_sensitive(text):
        return "", True
    if is_high_entropy(text):
        return "", True
    return clip_preview(text, limit), False
