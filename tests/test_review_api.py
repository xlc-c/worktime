"""Review API handlers, exercised without sockets (works on any platform)."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wt.config import load_config  # noqa: E402
from wt.review import ReviewHandler  # noqa: E402
from wt.store import Store  # noqa: E402

DATE = "2026-11-10"


def segment(matter="客户A / 对账", task="核对账目", app="Excel"):
    return {
        "date": DATE, "start_ts": f"{DATE}T09:00:00", "end_ts": f"{DATE}T10:00:00",
        "duration_s": 3600, "app": app, "title": "对账单.xlsx - Excel",
        "url": "", "page_title": "", "page_text": "", "focused_text": "",
        "clipboard_text": "", "auto_task": task, "auto_matter": matter,
        "confidence": 0.8, "final_task": task, "final_matter": matter,
        "evidence": "应用=Excel | 窗口=对账单.xlsx",
    }


class FakeHandler(ReviewHandler):
    """Bare handler with the store/cfg and captured JSON responses."""

    def __init__(self, store, cfg):
        self.store = store
        self.cfg = cfg
        self.default_date = DATE
        self.replies = []

    def _json(self, code, payload):
        self.replies.append((code, payload))

    def last(self):
        return self.replies[-1]


class ReviewApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="worktime-api-")
        self.cfg = load_config()
        self.cfg["_data_dir"] = self.tmp
        self.cfg["sync"]["folder"] = os.path.join(self.tmp, "sync")
        self.cfg["sync"]["enabled"] = True
        os.makedirs(self.cfg["sync"]["folder"], exist_ok=True)
        self.store = Store(os.path.join(self.tmp, "worktime.db"))
        self.store.replace_segments(DATE, [segment()])
        self.api = FakeHandler(self.store, self.cfg)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_rule_crud_and_preview(self):
        self.api._rule_save({"name": "excel 规则", "app": "excel",
                             "matter": "客户A / 对账"})
        code, payload = self.api.last()
        self.assertEqual(code, 200)
        self.assertEqual(len(payload["rules"]), 1)
        rule_id = payload["rule"]["id"]

        self.api._rule_preview({"app": "excel", "date": DATE})
        code, payload = self.api.last()
        self.assertEqual(payload["count"], 1)

        self.api._rule_suggest({"id": self.store.list_segments(DATE)[0]["id"]})
        code, payload = self.api.last()
        self.assertEqual(payload["rule"]["title"], "对账单")

        self.store.delete_rule(rule_id)
        self.assertEqual(self.store.list_rules(), [])

    def test_matter_and_invoice(self):
        self.api._matter_save({"path": "客户A", "rate": 800, "currency": "CNY"})
        code, payload = self.api.last()
        self.assertEqual(code, 200)
        self.assertEqual(payload["matters"][0]["rate"], 800.0)

        self.api._invoice_write({"date": DATE, "period": "day"})
        code, payload = self.api.last()
        self.assertTrue(payload["ok"])
        self.assertAlmostEqual(payload["total_amount"], 800.0)

    def test_sync_push_and_pull(self):
        self.api._sync_push({"days": 7})
        code, payload = self.api.last()
        self.assertEqual(code, 200)
        self.assertTrue(payload["path"].endswith(".wtb"))

        self.api._sync_pull({"days": 7})
        code, payload = self.api.last()
        self.assertEqual(code, 200)
        self.assertEqual(payload["files"], 0)  # own bundle is skipped

    def test_settings_payload_shape(self):
        payload = self.api._settings_payload()
        self.assertIn("sync", payload["effective"])
        self.assertIn("rules", payload)
        self.assertIn("matters", payload)
        self.assertIn("enterprise", payload["presets"])


if __name__ == "__main__":
    unittest.main()
