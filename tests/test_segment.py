"""Unit tests for segmentation rules."""

import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wt.segment import build_segments  # noqa: E402


def cfg():
    from wt.config import DEFAULTS, _deep_merge

    c = _deep_merge(DEFAULTS, {})
    c["_data_dir"] = "."
    return c


def rows(date, start, minutes, app, title, step=30):
    out = []
    begin = datetime.strptime(f"{date} {start}", "%Y-%m-%d %H:%M")
    end = begin + timedelta(minutes=minutes)
    cursor = begin
    while cursor < end:
        out.append({
            "ts": cursor.strftime("%Y-%m-%dT%H:%M:%S"),
            "app": app,
            "proc": app.lower() + ".exe",
            "title": title,
            "pid": 0,
            "idle_sec": 0.0,
            "screen": "active",
        })
        cursor += timedelta(seconds=step)
    return out


class SegmentTests(unittest.TestCase):
    def test_merges_same_window_and_tracks_gap(self):
        date = "2026-01-05"
        raw = rows(date, "09:00", 10, "Excel", "P1.xlsx - Excel")
        raw += rows(date, "10:00", 10, "Excel", "P1.xlsx - Excel")  # 50 min away
        segs = build_segments(raw, [], [], [], cfg())
        self.assertEqual(len(segs), 2)
        total = sum(s["duration_s"] for s in segs)
        self.assertGreaterEqual(total, 19 * 60)
        self.assertLessEqual(total, 21 * 60)

    def test_short_switch_is_absorbed(self):
        date = "2026-01-05"
        raw = rows(date, "09:00", 10, "Excel", "P1.xlsx - Excel")
        raw.append({
            "ts": f"{date}T09:10:10", "app": "Notepad", "proc": "notepad.exe",
            "title": "临时.txt - Notepad", "pid": 0, "idle_sec": 0.0, "screen": "active",
        })
        raw += rows(date, "09:10", 20, "Excel", "P1.xlsx - Excel")
        segs = build_segments(raw, [], [], [], cfg())
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0]["app"], "Excel")

    def test_browser_url_attached(self):
        date = "2026-01-05"
        raw = rows(date, "09:00", 10, "Edge", "订单 - Microsoft Edge")
        web = [{
            "ts": f"{date}T09:00:05",
            "browser": "Edge",
            "url": "https://erp.example.com/order/123",
            "page_title": "订单详情",
            "visible_text": "客户：华东贸易",
            "selection": "",
            "incognito": 0,
        }]
        segs = build_segments(raw, web, [], [], cfg())
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0]["url"], "https://erp.example.com/order/123")
        self.assertIn("网页=订单详情", segs[0]["evidence"])

    def test_clipboard_copy_paste_links_segments(self):
        date = "2026-01-05"
        raw = rows(date, "09:00", 10, "Edge", "供应商报价 - Microsoft Edge")
        raw += rows(date, "09:10", 10, "Excel", "P1.xlsx - Excel")
        clip = [
            {"ts": f"{date}T09:08:00", "text_hash": "abc", "preview": "报价 12.34",
             "app": "Edge", "title": "供应商报价", "chars": 10},
            {"ts": f"{date}T09:12:00", "text_hash": "abc", "preview": "报价 12.34",
             "app": "Excel", "title": "P1.xlsx", "chars": 10},
        ]
        segs = build_segments(raw, [], clip, [], cfg())
        links = {s["link_id"] for s in segs if s["link_id"]}
        self.assertEqual(len(links), 1)
        self.assertEqual(sum(1 for s in segs if s["link_id"]), 2)


if __name__ == "__main__":
    unittest.main()
