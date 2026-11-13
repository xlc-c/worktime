"""Billing: rate inheritance, hour rounding, invoice rendering."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wt.billing import (build_invoice, effective_rate, matter_chain,  # noqa: E402
                        render_invoice_markdown, round_hours, write_invoice)
from wt.config import load_config  # noqa: E402
from wt.store import Store  # noqa: E402

DATE = "2026-11-10"


def segment(matter, seconds, task="任务"):
    return {
        "date": DATE, "start_ts": f"{DATE}T09:00:00", "end_ts": f"{DATE}T10:00:00",
        "duration_s": seconds, "app": "Excel", "title": "t",
        "final_task": task, "final_matter": matter, "auto_task": task,
        "auto_matter": matter, "confidence": 0.9,
    }


class BillingTests(unittest.TestCase):
    def test_matter_chain(self):
        self.assertEqual(matter_chain("A / B / C"),
                         ["A / B / C", "A / B", "A"])
        self.assertEqual(matter_chain("A"), ["A"])
        self.assertEqual(matter_chain(""), [""])

    def test_rate_inherits_from_parent(self):
        rates = {"客户A": {"path": "客户A", "rate": 800.0, "currency": "CNY", "billable": 1}}
        entry = effective_rate("客户A / 项目B / 对账", rates)
        self.assertEqual(entry["rate"], 800.0)
        self.assertEqual(effective_rate("其他", rates), {})

    def test_round_hours(self):
        self.assertAlmostEqual(round_hours(1.04, 0), 1.04)
        self.assertAlmostEqual(round_hours(1.04, 6), 1.0)   # 6 min = 0.1h steps
        self.assertAlmostEqual(round_hours(1.08, 6), 1.1)
        self.assertAlmostEqual(round_hours(0.51, 30), 0.5)

    def test_invoice_totals(self):
        rates = {
            "客户A": {"path": "客户A", "rate": 800.0, "currency": "CNY", "billable": 1},
            "内部": {"path": "内部", "rate": 0.0, "currency": "CNY", "billable": 0},
        }
        segments = [
            segment("客户A / 对账", 3600),
            segment("客户A / 会议", 1800),
            segment("内部", 7200),
        ]
        invoice = build_invoice(segments, rates, round_minutes=0)
        self.assertAlmostEqual(invoice["total_hours"], 1.5)
        self.assertAlmostEqual(invoice["total_amount"], 1200.0)
        self.assertAlmostEqual(invoice["unbilled_seconds"], 7200.0)
        rows = {r["matter"]: r for r in invoice["rows"]}
        self.assertFalse(rows["内部"]["billable"])
        self.assertEqual(rows["内部"]["amount"], 0.0)

    def test_markdown_and_csv(self):
        rates = {"客户A": {"path": "客户A", "rate": 800.0, "billable": 1,
                           "currency": "CNY"}}
        invoice = build_invoice([segment("客户A", 3600)], rates)
        text = render_invoice_markdown(invoice, DATE, DATE)
        self.assertIn("计费工时", text)
        self.assertIn("800.00", text)
        self.assertIn("合计金额", text)


class InvoiceStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="worktime-inv-")
        self.cfg = load_config()
        self.cfg["_data_dir"] = self.tmp
        self.store = Store(os.path.join(self.tmp, "worktime.db"))

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_invoice_from_store(self):
        self.store.replace_segments(DATE, [segment("客户A / 对账", 5400)])
        self.store.upsert_matter("客户A", rate=600.0)
        out = write_invoice(self.store, self.cfg, DATE, "day")
        self.assertTrue(out["written"])
        self.assertTrue(os.path.isfile(out["markdown"]))
        self.assertTrue(os.path.isfile(out["csv"]))
        self.assertAlmostEqual(out["total_hours"], 1.5)
        self.assertAlmostEqual(out["total_amount"], 900.0)

    def test_matter_upsert_keeps_existing_rate(self):
        self.store.upsert_matter("客户B", rate=1200.0)
        self.store.upsert_matter("客户B", billable=False)
        matter = self.store.get_matter("客户B")
        self.assertAlmostEqual(matter["rate"], 1200.0)
        self.assertEqual(matter["billable"], 0)


if __name__ == "__main__":
    unittest.main()
