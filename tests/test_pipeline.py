"""End-to-end test: simulate a day, process it, produce reports."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wt.config import load_config  # noqa: E402
from wt.pipeline import process_date  # noqa: E402
from wt.report import write_report  # noqa: E402
from wt.simulate import simulate_day  # noqa: E402
from wt.store import Store  # noqa: E402


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="worktime-test-")
        self.cfg = load_config()
        self.cfg["_data_dir"] = self.tmp
        self.cfg["llm"]["enabled"] = False
        self.date = "2026-11-12"
        self.store = Store(os.path.join(self.tmp, "worktime.db"))

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_simulate_process_report(self):
        info = simulate_day(self.store, self.cfg, self.date)
        self.assertGreater(info["raw"], 1000)
        self.assertGreater(info["web"], 100)
        result = process_date(self.store, self.cfg, self.date, use_llm=False)
        self.assertGreater(result["segments"], 5)
        self.assertGreater(result["active_s"], 5 * 3600)
        self.assertLess(result["active_s"], 8 * 3600)
        segments = self.store.list_segments(self.date)
        self.assertTrue(all(s["final_task"] for s in segments))
        matters = {s["final_matter"] for s in segments}
        self.assertGreaterEqual(len(matters), 3)

        out = write_report(self.store, self.cfg, self.date)
        self.assertTrue(out["written"])
        self.assertTrue(os.path.isfile(out["markdown"]))
        self.assertTrue(os.path.isfile(out["csv"]))
        with open(out["markdown"], encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("按事项汇总", text)
        self.assertIn("时间线", text)

    def test_manual_labels_preserved_on_reprocess(self):
        simulate_day(self.store, self.cfg, self.date)
        process_date(self.store, self.cfg, self.date, use_llm=False)
        segments = self.store.list_segments(self.date)
        target = segments[0]
        self.store.update_segment(target["id"], "人工确认的任务", "人工确认的事项")
        process_date(self.store, self.cfg, self.date, use_llm=False)
        after = self.store.list_segments(self.date)
        matched = [
            s for s in after
            if s["final_task"] == "人工确认的任务" and s["final_matter"] == "人工确认的事项"
        ]
        self.assertTrue(matched, "manual label should survive reprocessing")


if __name__ == "__main__":
    unittest.main()
