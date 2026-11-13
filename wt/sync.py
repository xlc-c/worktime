"""Opt-in multi-device sync with per-channel manual selection.

Sync is **off by default and every channel is opt-in**. Some data is fine to
carry between machines (times, app names, matters), some is not (focused text,
clipboard previews, page bodies). This module keeps the decision explicit:

* ``sync.enabled``            master switch (default false)
* ``sync.channels.*``         one flag per data class (all default false except
                              times + matter names)
* ``sync.folder``             an ordinary folder you control (OneDrive, a USB
                              stick, Syncthing). Nothing is uploaded anywhere.
* ``sync.encrypt``            wrap the bundle with a passphrase (ChaCha20 +
                              HMAC, see :mod:`wt.crypto`)

Bundles are plain JSON (``.wtb``) or encrypted envelopes, so they can be
inspected before import. Imported days land in ``foreign_days`` — never mixed
into local segments, never editable by mistake, and idempotent per
``(device, date)``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from pathlib import Path

from . import crypto
from .config import data_paths
from .util import now_iso, shift_date, today_str

log = logging.getLogger("worktime.sync")

FORMAT = "worktime-bundle"
VERSION = 1
SUFFIX = ".wtb"

# channel -> what it unlocks. Keep the names user-facing: the UI renders them.
CHANNELS: dict[str, str] = {
    "times": "时间段与应用名（任何同步都需要）",
    "matters": "事项 / 任务名称与费率",
    "window_titles": "窗口标题",
    "urls": "网页地址与页面标题",
    "page_text": "网页正文",
    "focused_text": "焦点输入框文本",
    "clipboard": "剪贴板预览",
}

DEFAULT_CHANNELS = {
    "times": True,
    "matters": True,
    "window_titles": False,
    "urls": False,
    "page_text": False,
    "focused_text": False,
    "clipboard": False,
}


def channel_config(cfg: dict) -> dict:
    sync = cfg.get("sync") or {}
    merged = dict(DEFAULT_CHANNELS)
    for key, value in (sync.get("channels") or {}).items():
        if key in CHANNELS:
            merged[key] = bool(value)
    merged["times"] = True  # a bundle without times is meaningless
    return merged


def enabled_channels(cfg: dict) -> list[str]:
    return [name for name, on in channel_config(cfg).items() if on]


def device_identity(store, cfg: dict) -> tuple[str, str]:
    """Stable per-install device id, stored in the local DB."""
    sync = cfg.get("sync") or {}
    device_id = str(sync.get("device_id") or store.get_meta("device.id", "")).strip()
    if not device_id:
        device_id = "dev-" + uuid.uuid4().hex[:8]
        store.set_meta("device.id", device_id)
    name = str(sync.get("device_name") or store.get_meta("device.name", "")).strip()
    if not name:
        try:
            name = os.environ.get("COMPUTERNAME") or os.uname().nodename
        except Exception:
            name = ""
        name = (name or "").strip() or device_id
        store.set_meta("device.name", name[:60])
    return device_id, name[:60]


def _strip_evidence(seg: dict, channels: dict) -> str:
    parts = [f"应用={seg.get('app', '')}"]
    if channels.get("window_titles") and seg.get("title"):
        parts.append(f"窗口={seg['title']}")
    if channels.get("urls") and seg.get("page_title"):
        parts.append(f"网页={str(seg['page_title'])[:120]}")
    return " | ".join(parts)


def sanitize_segment(seg: dict, channels: dict) -> dict:
    """Drop every field the user did not opt into."""
    item = {
        "start_ts": seg.get("start_ts", ""),
        "end_ts": seg.get("end_ts", ""),
        "duration_s": seg.get("duration_s", 0.0),
        "kind": seg.get("kind", "work"),
        "app": seg.get("app", ""),
    }
    if channels.get("window_titles"):
        item["title"] = seg.get("title", "")
    if channels.get("urls"):
        item["url"] = seg.get("url", "")
        item["page_title"] = seg.get("page_title", "")
    if channels.get("page_text"):
        item["page_text"] = seg.get("page_text", "")
    if channels.get("focused_text"):
        item["focused_text"] = seg.get("focused_text", "")
    if channels.get("clipboard"):
        item["clipboard_text"] = seg.get("clipboard_text", "")
    if channels.get("matters"):
        item["task"] = seg.get("final_task") or seg.get("auto_task") or ""
        item["matter"] = seg.get("final_matter") or seg.get("auto_matter") or ""
        item["confidence"] = seg.get("confidence") or 0
    item["evidence"] = _strip_evidence(seg, channels)
    return item


def collect_days(store, cfg: dict, start: str, end: str, channels: dict | None = None) -> dict:
    channels = channels or channel_config(cfg)
    days: dict[str, list[dict]] = {}
    for seg in store.fetch_segments_between(start, end):
        day = seg["date"]
        days.setdefault(day, []).append(sanitize_segment(seg, channels))
    return days


def build_bundle(store, cfg: dict, start: str, end: str,
                 channels: dict | None = None) -> dict:
    channels = channels or channel_config(cfg)
    device_id, device_name = device_identity(store, cfg)
    matters = []
    if channels.get("matters"):
        matters = [
            {
                "path": m["path"],
                "rate": m.get("rate") or 0,
                "currency": m.get("currency") or "CNY",
                "billable": int(m.get("billable") if m.get("billable") is not None else 1),
            }
            for m in store.list_matters()
        ]
    return {
        "format": FORMAT,
        "version": VERSION,
        "device": {"id": device_id, "name": device_name},
        "created_ts": now_iso(),
        "range": {"start": start, "end": end},
        "channels": channels,
        "matters": matters,
        "days": collect_days(store, cfg, start, end, channels),
    }


def encode_bundle(bundle: dict, passphrase: str | None = None) -> bytes:
    payload = json.dumps(bundle, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8")
    if passphrase:
        return crypto.encrypt_bytes(payload, passphrase)
    return payload


def decode_bundle(blob: bytes, passphrase: str | None = None) -> dict:
    if crypto.is_encrypted(blob):
        if not passphrase:
            raise ValueError("这个同步包已加密，需要密码")
        blob = crypto.decrypt_bytes(blob, passphrase)
    try:
        data = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("同步包格式不对") from exc
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("不是 WorkTime 同步包")
    if int(data.get("version") or 0) > VERSION:
        raise ValueError("同步包版本比本机新，请先升级 WorkTime")
    return data


def preview(store, cfg: dict, days: int = 7, channels: dict | None = None) -> dict:
    """What would leave this machine — computed on the real payload."""
    channels = channels or channel_config(cfg)
    end = today_str()
    start = shift_date(end, -(max(1, int(days)) - 1))
    bundle = build_bundle(store, cfg, start, end, channels)
    total_segments = sum(len(v) for v in bundle["days"].values())
    samples = []
    for day in sorted(bundle["days"])[-2:]:
        for seg in bundle["days"][day][:3]:
            samples.append({
                "day": day,
                "start": seg["start_ts"][11:16],
                "app": seg["app"],
                "title": seg.get("title", ""),
                "matter": seg.get("matter", ""),
            })
    return {
        "range": {"start": start, "end": end},
        "days": len(bundle["days"]),
        "segments": total_segments,
        "channels": channels,
        "enabled_channels": [k for k, v in channels.items() if v],
        "matters": len(bundle["matters"]),
        "samples": samples,
        "bytes": len(encode_bundle(bundle)),
    }


def export_to_file(store, cfg: dict, days: int = 7, out_dir: str | None = None,
                   passphrase: str | None = None,
                   end: str | None = None) -> dict:
    end = end or today_str()
    start = shift_date(end, -(max(1, int(days)) - 1))
    bundle = build_bundle(store, cfg, start, end)
    blob = encode_bundle(bundle, passphrase)
    target_dir = Path(out_dir or (cfg.get("sync") or {}).get("folder")
                      or str(data_paths(cfg)["exports"]))
    target_dir.mkdir(parents=True, exist_ok=True)
    name = f"{bundle['device']['id']}-{end}{SUFFIX}"
    path = target_dir / name
    path.write_bytes(blob)
    digest = hashlib.sha256(blob).hexdigest()
    store.mark_sync_file(digest, str(path), "export")
    return {
        "path": str(path), "bytes": len(blob), "sha256": digest,
        "range": {"start": start, "end": end},
        "days": len(bundle["days"]),
        "encrypted": bool(passphrase),
        "segments": sum(len(v) for v in bundle["days"].values()),
    }


def import_bundle(store, cfg: dict, bundle: dict, source: str = "file",
                  passphrase: str | None = None) -> dict:
    channels = bundle.get("channels") or {}
    own_id, _ = device_identity(store, cfg)
    source_device = str((bundle.get("device") or {}).get("id") or "")
    if source_device and source_device == own_id:
        return {"imported": 0, "skipped": "own bundle", "days": []}
    imported = []
    for day, segments in (bundle.get("days") or {}).items():
        if not segments:
            continue
        normalized = []
        for seg in segments:
            item = dict(seg)
            # bundle fields are channel names; reports read the pipeline names
            item.setdefault("final_matter", item.get("matter", "") or "")
            item.setdefault("final_task", item.get("task", "") or "")
            item.setdefault("auto_matter", item.get("matter", "") or "")
            item.setdefault("auto_task", item.get("task", "") or "")
            item["date"] = str(day)
            normalized.append(item)
        store.import_foreign_day(
            source_device or "unknown",
            str((bundle.get("device") or {}).get("name") or "")[:60],
            str(day),
            normalized,
            bundle.get("created_ts") or "",
        )
        imported.append(day)
    for matter in bundle.get("matters") or []:
        path = str(matter.get("path") or "").strip()
        if not path:
            continue
        current = store.get_matter(path)
        if current:
            continue  # never overwrite local rates silently
        store.upsert_matter(
            path,
            rate=float(matter.get("rate") or 0),
            currency=str(matter.get("currency") or "CNY"),
            billable=bool(matter.get("billable", 1)),
            note="来自同步",
        )
    return {
        "imported": len(imported),
        "days": sorted(imported),
        "skipped": "",
        "device": source_device,
        "device_name": (bundle.get("device") or {}).get("name") or "",
        "channels": channels,
    }


def import_file(store, cfg: dict, path: str, passphrase: str | None = None) -> dict:
    blob = Path(path).read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    if store.sync_seen(digest):
        return {"imported": 0, "skipped": "already imported", "days": []}
    bundle = decode_bundle(blob, passphrase)
    result = import_bundle(store, cfg, bundle, source=path)
    store.mark_sync_file(digest, str(path), "import")
    return result


def push_folder(store, cfg: dict, days: int = 7,
                passphrase: str | None = None) -> dict:
    sync = cfg.get("sync") or {}
    folder = str(sync.get("folder") or "").strip()
    if not folder:
        raise ValueError("sync.folder 未设置：请先选择一个同步文件夹")
    if not sync.get("enabled"):
        raise ValueError("同步未开启（sync.enabled = false）")
    return export_to_file(store, cfg, days=days, out_dir=folder, passphrase=passphrase)


def pull_folder(store, cfg: dict, passphrase: str | None = None,
                limit: int = 200) -> dict:
    sync = cfg.get("sync") or {}
    folder = Path(str(sync.get("folder") or "").strip())
    if not folder or not str(folder):
        raise ValueError("sync.folder 未设置")
    if not sync.get("enabled"):
        raise ValueError("同步未开启（sync.enabled = false）")
    if not folder.is_dir():
        raise ValueError(f"同步文件夹不存在：{folder}")
    imported = []
    skipped = []
    for path in sorted(folder.glob("*" + SUFFIX))[:limit]:
        try:
            result = import_file(store, cfg, str(path), passphrase)
        except ValueError as exc:
            skipped.append({"file": path.name, "error": str(exc)})
            continue
        if result.get("imported"):
            imported.append({"file": path.name, **result})
    return {"imported": imported, "skipped": skipped,
            "files": len(imported), "days": sum(r["imported"] for r in imported)}


def status(store, cfg: dict) -> dict:
    sync = cfg.get("sync") or {}
    today = today_str()
    end = today
    start = shift_date(end, -6)
    return {
        "enabled": bool(sync.get("enabled")),
        "folder": sync.get("folder") or "",
        "encrypt": bool(sync.get("encrypt")),
        "channels": channel_config(cfg),
        "device": {"id": store.get_meta("device.id", ""),
                   "name": store.get_meta("device.name", "")},
        "local_days": len({s["date"] for s in store.fetch_segments_between(start, end)}),
        "foreign_days": store.foreign_day_count(),
        "foreign_range": _foreign_range(store),
    }


def _foreign_range(store) -> dict:
    days = store.list_foreign_days()
    if not days:
        return {"start": "", "end": "", "devices": []}
    devices = sorted({d["device_id"] for d in days})
    return {"start": days[0]["date"], "end": days[-1]["date"], "devices": devices}
