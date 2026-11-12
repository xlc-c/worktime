"""Tests for capture/permission presets."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wt.policy import PRESETS, apply_policy, summarize  # noqa: E402


def base(preset):
    return {
        "policy": {"preset": preset, "locked": False},
        "capture": {},
        "display": {},
        "privacy": {},
    }


class PolicyTests(unittest.TestCase):
    def test_strict_disables_all_content(self):
        out = apply_policy(base("strict"), {"policy": {"preset": "strict"}})
        for key in ("window_titles", "browser_titles", "browser_urls",
                    "browser_page_text", "focused_text", "clipboard"):
            self.assertFalse(out["capture"][key], key)
        self.assertFalse(out["display"]["allow_content_toggle"])
        self.assertEqual(out["capture"]["clipboard_preview_chars"], 0)

    def test_metadata_keeps_titles_and_urls_only(self):
        out = apply_policy(base("metadata"), {"policy": {"preset": "metadata"}})
        self.assertTrue(out["capture"]["window_titles"])
        self.assertTrue(out["capture"]["browser_urls"])
        self.assertFalse(out["capture"]["browser_page_text"])
        self.assertFalse(out["capture"]["focused_text"])
        self.assertFalse(out["capture"]["clipboard"])

    def test_standard_enables_content(self):
        out = apply_policy(base("standard"), {"policy": {"preset": "standard"}})
        self.assertTrue(out["capture"]["browser_page_text"])
        self.assertTrue(out["capture"]["focused_text"])
        self.assertTrue(out["capture"]["clipboard"])
        self.assertEqual(out["display"]["show_content_default"], False)
        self.assertTrue(out["display"]["allow_content_toggle"])

    def test_user_override_beats_preset(self):
        override = {"capture": {"clipboard": False}, "privacy": {"retention_days": 3}}
        out = apply_policy(base("standard"), override)
        self.assertFalse(out["capture"]["clipboard"])
        self.assertEqual(out["privacy"]["retention_days"], 3)
        self.assertTrue(out["capture"]["browser_page_text"])

    def test_unknown_preset_falls_back_to_standard(self):
        out = apply_policy(base("nope"), {"policy": {"preset": "nope"}})
        self.assertEqual(out["policy"]["preset"], "standard")
        self.assertTrue(out["capture"]["window_titles"])

    def test_summarize(self):
        out = apply_policy(base("metadata"), {"policy": {"preset": "metadata"}})
        summary = summarize(out)
        self.assertIn("窗口标题", summary["enabled"])
        self.assertNotIn("剪贴板", summary["enabled"])
        self.assertEqual(summary["preset"], "metadata")
        self.assertFalse(summary["allow_content_toggle"])

    def test_all_presets_have_required_sections(self):
        for name, preset in PRESETS.items():
            for section in ("capture", "display", "privacy"):
                self.assertIn(section, preset, f"{name}.{section}")


if __name__ == "__main__":
    unittest.main()
