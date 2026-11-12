"""Unit tests for clustering / labeling."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wt.classify import (  # noqa: E402
    ID_RE,
    _clean_title,
    deterministic_label,
    label_segments,
    primary_key,
)


def seg(app, title, url="", page_title="", duration=600, link_id=""):
    return {
        "app": app,
        "title": title,
        "url": url,
        "page_title": page_title,
        "page_text": "",
        "focused_text": "",
        "clipboard_text": "",
        "duration_s": duration,
        "link_id": link_id,
    }


def cfg():
    from wt.config import DEFAULTS, _deep_merge

    c = _deep_merge(DEFAULTS, {})
    c["_data_dir"] = "."
    return c


class ClassifyTests(unittest.TestCase):
    def test_id_regex_keeps_full_order_number(self):
        found = ID_RE.findall("订单 20241112-0032 金额 12345.67")
        self.assertIn("20241112-0032", found)

    def test_clean_title_strips_app_suffix(self):
        self.assertEqual(_clean_title("P2401_成本测算.xlsx - Excel", "Excel"), "P2401_成本测算.xlsx")
        self.assertEqual(_clean_title("Re: 华东贸易对账 - 邮箱", "Chrome"), "华东贸易对账")

    def test_primary_key_distinguishes_files(self):
        a = seg("Excel", "P2401_成本测算.xlsx - Excel")
        b = seg("Excel", "P2402_回款台账.xlsx - Excel")
        self.assertNotEqual(primary_key(a), primary_key(b))

    def test_alias_applied(self):
        segments = [
            seg("Excel", "P2401_成本测算.xlsx - Excel"),
            seg("Excel", "P2401_成本测算.xlsx - Excel"),
        ]
        aliases = [{"kind": "title", "pattern": "p2401_成本测算.xlsx",
                    "task": "核算成本", "matter": "P2401 成本测算"}]
        label_segments(segments, cfg(), aliases, None)
        for s in segments:
            self.assertEqual(s["auto_task"], "核算成本")
            self.assertEqual(s["auto_matter"], "P2401 成本测算")
            self.assertEqual(s["confidence"], 0.99)

    def test_different_files_not_merged(self):
        segments = [
            seg("Excel", "P2401_成本测算.xlsx - Excel", duration=600),
            seg("Excel", "P2402_回款台账.xlsx - Excel", duration=600),
        ]
        label_segments(segments, cfg(), [], None)
        self.assertNotEqual(segments[0]["auto_matter"], segments[1]["auto_matter"])

    def test_deterministic_label_uses_longest_title(self):
        task, matter, conf = deterministic_label([
            seg("Excel", "P2401_成本测算.xlsx - Excel", duration=300),
            seg("Edge", "供应商报价 Q-8891", duration=1800),
        ])
        self.assertIn("Q-8891", matter)
        self.assertEqual(conf, 0.35)


if __name__ == "__main__":
    unittest.main()
