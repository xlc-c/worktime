"""Explicit rules: matching, priority, and integration with the pipeline."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wt.config import load_config  # noqa: E402
from wt.pipeline import process_date  # noqa: E402
from wt.rules import (apply_rules, preview_rule, rule_matches,  # noqa: E402
                      sort_rules, suggest_rule)
from wt.simulate import simulate_day  # noqa: E402
from wt.store import Store  # noqa: E402


def seg(**kw):
    base = {
        "app": "Excel", "title": "2026-11 对账单 - Excel", "url": "",
        "page_title": "", "focused_text": "", "duration_s": 600,
        "start_ts": "2026-11-12T09:00:00", "end_ts": "2026-11-12T09:10:00",
    }
    base.update(kw)
    return base


class RuleMatchTests(unittest.TestCase):
    def test_contains_and_case_insensitive(self):
        rule = {"app": "excel", "title": "对账", "matter": "客户A"}
        self.assertTrue(rule_matches(rule, seg()))
        self.assertFalse(rule_matches(rule, seg(title="周报 - Excel")))

    def test_exact_and_regex(self):
        self.assertTrue(rule_matches({"app": "=excel", "matter": "x"}, seg()))
        self.assertFalse(rule_matches({"app": "=exce", "matter": "x"}, seg()))
        self.assertTrue(rule_matches({"title": r"re:对账(单|表)", "matter": "x"}, seg()))
        self.assertFalse(rule_matches({"title": "re:[", "matter": "x"}, seg()))

    def test_domain_and_focused(self):
        rule = {"url_domain": "example.com", "matter": "客户B"}
        site = seg(app="Chrome", url="https://example.com/invoice/1", title="发票")
        self.assertTrue(rule_matches(rule, site))
        self.assertFalse(rule_matches(rule, seg(app="Chrome", url="https://other.org/x")))
        self.assertTrue(rule_matches({"focused": "合同", "matter": "x"},
                                     seg(focused_text="这是一份合同内容")))

    def test_no_condition_never_matches(self):
        self.assertFalse(rule_matches({"matter": "x"}, seg()))

    def test_priority_order_and_first_match_wins(self):
        segments = [seg()]
        rules = [
            {"id": 1, "name": "low", "priority": 10, "app": "excel", "matter": "低"},
            {"id": 2, "name": "high", "priority": 200, "app": "excel", "matter": "高"},
        ]
        hits = apply_rules(segments, rules)
        self.assertEqual(segments[0]["auto_matter"], "高")
        self.assertEqual(segments[0]["rule_name"], "high")
        self.assertEqual(hits, {2: 1})

    def test_disabled_rule_ignored(self):
        segments = [seg()]
        apply_rules(segments, [{"id": 3, "enabled": 0, "app": "excel", "matter": "x"}])
        self.assertNotIn("rule_name", segments[0])
        self.assertEqual(sort_rules([{"id": 3, "enabled": 0}]), [])

    def test_matter_only_rule_still_names_the_task(self):
        segments = [seg(title="2026-11 对账单 - Excel")]
        apply_rules(segments, [{"id": 4, "title": "对账", "matter": "客户A"}])
        self.assertEqual(segments[0]["auto_matter"], "客户A")
        self.assertTrue(segments[0]["auto_task"])
        self.assertGreaterEqual(segments[0]["confidence"], 0.9)

    def test_preview_and_suggest(self):
        segments = [seg(), seg(title="周报 - Excel")]
        result = preview_rule({"app": "excel", "matter": "x"}, segments)
        self.assertEqual(result["count"], 2)
        rule = suggest_rule(seg(), matter="客户A")
        self.assertEqual(rule["title"], "2026-11 对账单")
        self.assertEqual(rule["matter"], "客户A")


class RulePipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="worktime-rule-")
        self.cfg = load_config()
        self.cfg["_data_dir"] = self.tmp
        self.cfg["llm"]["enabled"] = False
        self.date = "2026-11-12"
        self.store = Store(os.path.join(self.tmp, "worktime.db"))

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_process_applies_rule_and_counts_hits(self):
        simulate_day(self.store, self.cfg, self.date)
        rule = self.store.upsert_rule({
            "name": "所有 Excel 都算对账", "app": "excel",
            "matter": "客户A / 对账", "task": "核对账目",
        })
        result = process_date(self.store, self.cfg, self.date, use_llm=False)
        self.assertGreater(result["rules_hit"], 0)
        segments = self.store.list_segments(self.date)
        ruled = [s for s in segments if s["rule_name"]]
        self.assertTrue(ruled)
        self.assertTrue(all(s["auto_matter"] == "客户A / 对账" for s in ruled))
        self.assertGreater(self.store.list_rules()[0]["matches"], 0)

    def test_manual_label_beats_rule_on_reprocess(self):
        simulate_day(self.store, self.cfg, self.date)
        self.store.upsert_rule({"name": "excel", "app": "excel", "matter": "规则事项"})
        process_date(self.store, self.cfg, self.date, use_llm=False)
        segments = self.store.list_segments(self.date)
        target = next(s for s in segments if s.get("rule_name"))
        self.store.update_segment(target["id"], "人工任务", "人工事项")
        process_date(self.store, self.cfg, self.date, use_llm=False)
        after = [s for s in self.store.list_segments(self.date)
                 if s["final_matter"] == "人工事项"]
        self.assertTrue(after)

    def test_toggle_preserves_conditions(self):
        rule = self.store.upsert_rule({"name": "excel", "app": "excel",
                                       "matter": "客户A", "task": "对账"})
        # the UI sends {id, enabled} only when flipping the switch
        self.store.upsert_rule({"id": rule["id"], "enabled": False})
        after = self.store.get_rule(rule["id"])
        self.assertEqual(after["enabled"], 0)
        self.assertEqual(after["app"], "excel")
        self.assertEqual(after["matter"], "客户A")
        self.assertEqual(after["task"], "对账")


if __name__ == "__main__":
    unittest.main()
