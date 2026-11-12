"""Capture/permission presets.

Different people and companies have different rules: some can store window titles
and page text, some can only store app names and durations. A preset bundles the
capture scope, retention and content-display switches; explicit values in
config.json override the preset, so IT can start from a preset and tighten it.

Presets are not a security boundary on a local machine (the user owns the
files), but they make the intended policy explicit and prevent accidental
over-collection in the UI.
"""

from __future__ import annotations

import copy

PRESETS: dict[str, dict] = {
    # Time only: no titles, no URLs, no page text, no clipboard, no focused text.
    "strict": {
        "capture": {
            "window_titles": False,
            "browser_titles": False,
            "browser_urls": False,
            "browser_page_text": False,
            "focused_text": False,
            "clipboard": False,
            "clipboard_preview_chars": 0,
            "idle": True,
        },
        "privacy": {"retention_days": 7, "store_raw_clipboard_days": 0},
        "display": {"show_content_default": False, "allow_content_toggle": False},
    },
    # App + title + domain/URL metadata, but no page body, clipboard or UI text.
    "metadata": {
        "capture": {
            "window_titles": True,
            "browser_titles": True,
            "browser_urls": True,
            "browser_page_text": False,
            "focused_text": False,
            "clipboard": False,
            "clipboard_preview_chars": 0,
            "idle": True,
        },
        "privacy": {"retention_days": 14, "store_raw_clipboard_days": 0},
        "display": {"show_content_default": False, "allow_content_toggle": False},
    },
    # Default: titles + URLs + page text + focused text + clipboard preview.
    "standard": {
        "capture": {
            "window_titles": True,
            "browser_titles": True,
            "browser_urls": True,
            "browser_page_text": True,
            "focused_text": True,
            "clipboard": True,
            "clipboard_preview_chars": 240,
            "idle": True,
        },
        "privacy": {"retention_days": 30, "store_raw_clipboard_days": 7},
        "display": {"show_content_default": False, "allow_content_toggle": True},
    },
    # Same scope, longer previews and retention (personal use).
    "full": {
        "capture": {
            "window_titles": True,
            "browser_titles": True,
            "browser_urls": True,
            "browser_page_text": True,
            "focused_text": True,
            "clipboard": True,
            "clipboard_preview_chars": 500,
            "idle": True,
        },
        "privacy": {"retention_days": 90, "store_raw_clipboard_days": 30},
        "display": {"show_content_default": False, "allow_content_toggle": True},
    },
}

SECTIONS = ("capture", "display", "privacy")


def apply_policy(cfg: dict, override: dict | None = None) -> dict:
    """Merge the selected preset into cfg; explicit override values win."""
    override = override or {}
    policy_override = override.get("policy") or {}
    preset_name = policy_override.get("preset") or (cfg.get("policy") or {}).get("preset") or "standard"
    preset = PRESETS.get(preset_name, PRESETS["standard"])
    for section in SECTIONS:
        merged = copy.deepcopy(preset.get(section, {}))
        # explicit user/IT overrides from config.json win over the preset
        for key, value in (override.get(section) or {}).items():
            merged[key] = value
        cfg[section] = merged
    cfg["policy"] = {
        **(cfg.get("policy") or {}),
        **policy_override,
        "preset": preset_name if preset_name in PRESETS else "standard",
    }
    cfg["_policy"] = {
        "preset": cfg["policy"]["preset"],
        "locked": bool(cfg["policy"].get("locked")),
        "presets": list(PRESETS),
    }
    return cfg


def summarize(cfg: dict) -> dict:
    capture = cfg.get("capture", {})
    privacy = cfg.get("privacy", {})
    display = cfg.get("display", {})
    enabled = [label for key, label in (
        ("window_titles", "窗口标题"),
        ("browser_urls", "浏览器 URL"),
        ("browser_page_text", "网页正文"),
        ("focused_text", "焦点输入"),
        ("clipboard", "剪贴板"),
    ) if capture.get(key)]
    return {
        "preset": (cfg.get("policy") or {}).get("preset", "standard"),
        "locked": bool((cfg.get("policy") or {}).get("locked")),
        "enabled": enabled,
        "retention_days": privacy.get("retention_days"),
        "clipboard_days": privacy.get("store_raw_clipboard_days"),
        "show_content_default": display.get("show_content_default"),
        "allow_content_toggle": display.get("allow_content_toggle"),
        "excluded_apps": privacy.get("excluded_apps") or [],
        "excluded_domains": privacy.get("excluded_domains") or [],
    }
