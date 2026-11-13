"""Opt-in sync: channel filtering, encryption, import idempotency, reports."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wt import crypto, sync  # noqa: E402
from wt.config import load_config  # noqa: E402
from wt.report import summarize_period, write_period_report  # noqa: E402
from wt.store import Store  # noqa: E402

DATE = "2026-11-10"


def make_store(tmp, name):
    return Store(os.path.join(tmp, name))


def add_day(store, date=DATE, matter="客户A / 对账", task="核对账目"):
    segments = [
        {
            "date": date,
            "start_ts": f"{date}T09:00:00", "end_ts": f"{date}T09:30:00",
            "duration_s": 1800, "kind": "work", "app": "Excel",
            "title": "对账单.xlsx - Excel", "url": "",
            "page_title": "", "page_text": "",
            "focused_text": "华东贸易 2026-11 对账", "clipboard_text": "订单号 A123",
            "link_id": "", "auto_task": task, "auto_matter": matter,
            "confidence": 0.9, "final_task": task, "final_matter": matter,
            "evidence": "应用=Excel | 窗口=对账单.xlsx",
        },
        {
            "date": date,
            "start_ts": f"{date}T10:00:00", "end_ts": f"{date}T11:00:00",
            "duration_s": 3600, "kind": "work", "app": "Chrome",
            "title": "发票查询 - Chrome", "url": "https://example.com/invoice/9",
            "page_title": "发票查询", "page_text": "页面正文示例",
            "focused_text": "", "clipboard_text": "",
            "link_id": "", "auto_task": "查发票", "auto_matter": "客户B",
            "confidence": 0.6, "final_task": "查发票", "final_matter": "客户B",
            "evidence": "应用=Chrome | 网页=发票查询",
        },
    ]
    store.replace_segments(date, segments)


class SyncChannelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="worktime-sync-")
        self.cfg = load_config()
        self.cfg["_data_dir"] = self.tmp
        self.store = make_store(self.tmp, "a.db")

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_channels_are_minimal(self):
        channels = sync.channel_config(self.cfg)
        self.assertTrue(channels["times"])
        self.assertTrue(channels["matters"])
        self.assertFalse(channels["window_titles"])
        self.assertFalse(channels["focused_text"])
        self.assertFalse(channels["clipboard"])

    def test_bundle_strips_unselected_channels(self):
        add_day(self.store)
        bundle = sync.build_bundle(self.store, self.cfg, DATE, DATE)
        segs = bundle["days"][DATE]
        self.assertEqual(len(segs), 2)
        self.assertNotIn("title", segs[0])
        self.assertNotIn("focused_text", segs[0])
        self.assertNotIn("clipboard_text", segs[0])
        self.assertNotIn("url", segs[1])
        self.assertNotIn("page_text", segs[1])
        self.assertEqual(segs[0]["matter"], "客户A / 对账")
        self.assertNotIn("华东贸易", str(bundle))

    def test_enabling_channels_keeps_content(self):
        self.cfg["sync"]["channels"].update({
            "window_titles": True, "urls": True, "focused_text": True,
            "clipboard": True, "page_text": True,
        })
        add_day(self.store)
        bundle = sync.build_bundle(self.store, self.cfg, DATE, DATE)
        seg = bundle["days"][DATE][0]
        self.assertEqual(seg["title"], "对账单.xlsx - Excel")
        self.assertEqual(seg["focused_text"], "华东贸易 2026-11 对账")
        self.assertEqual(seg["clipboard_text"], "订单号 A123")

    def test_times_always_enabled(self):
        self.cfg["sync"]["channels"]["times"] = False
        self.assertTrue(sync.channel_config(self.cfg)["times"])

    def test_encrypt_roundtrip_and_wrong_passphrase(self):
        add_day(self.store)
        bundle = sync.build_bundle(self.store, self.cfg, DATE, DATE)
        blob = sync.encode_bundle(bundle, "s3cret")
        self.assertTrue(crypto.is_encrypted(blob))
        self.assertNotIn("对账".encode("utf-8"), blob)
        back = sync.decode_bundle(blob, "s3cret")
        self.assertEqual(back["days"][DATE][0]["matter"], "客户A / 对账")
        with self.assertRaises(ValueError):
            sync.decode_bundle(blob, "wrong")
        with self.assertRaises(ValueError):
            sync.decode_bundle(blob, "")

    def test_import_is_idempotent_and_marks_foreign(self):
        add_day(self.store)
        bundle = sync.build_bundle(self.store, self.cfg, DATE, DATE)
        target = make_store(self.tmp, "b.db")
        try:
            first = sync.import_bundle(target, self.cfg, bundle)
            self.assertEqual(first["imported"], 1)
            second = sync.import_bundle(target, self.cfg, bundle)
            self.assertEqual(second["imported"], 1)  # same device+date only replaces
            self.assertEqual(target.foreign_day_count(), 1)
            foreign = target.foreign_segments_between(DATE, DATE)
            self.assertEqual(len(foreign), 2)
            self.assertTrue(foreign[0]["foreign"])
            self.assertTrue(foreign[0]["device_id"].startswith("dev-"))
            # local timeline untouched
            self.assertEqual(target.list_segments(DATE), [])
        finally:
            target.close()

    def test_own_bundle_not_imported(self):
        add_day(self.store)
        bundle = sync.build_bundle(self.store, self.cfg, DATE, DATE)
        result = sync.import_bundle(self.store, self.cfg, bundle)
        self.assertEqual(result["imported"], 0)
        self.assertEqual(result["skipped"], "own bundle")

    def test_export_and_import_file(self):
        add_day(self.store)
        out = sync.export_to_file(self.store, self.cfg, days=7, out_dir=self.tmp,
                                  end=DATE)
        self.assertTrue(os.path.isfile(out["path"]))
        self.assertEqual(out["days"], 1)
        target = make_store(self.tmp, "c.db")
        try:
            result = sync.import_file(target, self.cfg, out["path"])
            self.assertEqual(result["imported"], 1)
            self.assertEqual(target.foreign_day_count(), 1)
            # importing the same file again is a no-op
            again = sync.import_file(target, self.cfg, out["path"])
            self.assertEqual(again["imported"], 0)
            self.assertEqual(again["skipped"], "already imported")
        finally:
            target.close()

    def test_preview_reports_counts(self):
        add_day(self.store)
        info = sync.preview(self.store, self.cfg, days=30)
        self.assertEqual(info["segments"], 2)
        self.assertGreater(info["bytes"], 0)
        self.assertIn("times", info["enabled_channels"])


class SyncReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="worktime-sync-rpt-")
        self.cfg = load_config()
        self.cfg["_data_dir"] = self.tmp
        self.cfg["sync"]["enabled"] = True
        self.store = make_store(self.tmp, "local.db")
        add_day(self.store)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_foreign_days_join_period_report_when_sync_enabled(self):
        remote = make_store(self.tmp, "remote.db")
        try:
            add_day(remote, date="2026-11-11", matter="客户C", task="远程任务")
            bundle = sync.build_bundle(remote, self.cfg, "2026-11-11", "2026-11-11")
            sync.import_bundle(self.store, self.cfg, bundle)
        finally:
            remote.close()
        out = write_period_report(self.store, self.cfg, DATE, "week")
        self.assertTrue(out["written"])
        self.assertEqual(out["foreign_days"], 1)
        with open(out["markdown"], encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("客户C", text)

    def test_foreign_excluded_when_sync_disabled(self):
        remote = make_store(self.tmp, "remote2.db")
        try:
            add_day(remote, date="2026-11-11", matter="客户C", task="远程任务")
            bundle = sync.build_bundle(remote, self.cfg, "2026-11-11", "2026-11-11")
            sync.import_bundle(self.store, self.cfg, bundle)
        finally:
            remote.close()
        from wt.report import report_segments

        _, with_sync = report_segments(self.store, self.cfg, DATE, "2026-11-12")
        self.assertEqual(len(with_sync), 2)
        self.cfg["sync"]["enabled"] = False
        _, without_sync = report_segments(self.store, self.cfg, DATE, "2026-11-12")
        self.assertEqual(without_sync, [])


if __name__ == "__main__":
    unittest.main()
