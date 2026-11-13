"""Cross-platform raw import: Android/other collectors -> desktop pipeline."""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wt.config import load_config  # noqa: E402
from wt.importers import (RawFormatError, import_document,  # noqa: E402
                          import_file, validate_document)
from wt.pipeline import process_date  # noqa: E402
from wt.store import Store  # noqa: E402

DATE = "2026-11-13"


def raw_doc(rows=None, date=DATE):
    rows = rows or [
        ("09:00:00", "微信", "com.tencent.mm"),
        ("09:20:00", "Excel", "com.microsoft.office.excel"),
        ("10:00:00", "微信", "com.tencent.mm"),
        ("11:00:00", "Chrome", "com.android.chrome"),
    ]
    activity = [
        {
            "ts": f"{date}T{stamp}", "app": app, "proc": proc,
            "title": "", "pid": 0, "idle_sec": 0, "screen": "active",
        }
        for stamp, app, proc in rows
    ]
    return {
        "format": "worktime-raw", "version": 1, "platform": "android",
        "device": {"id": "dev-test", "name": "SM-S9280"},
        "exported_at": f"{date}T12:00:00",
        "days": {date: {"activity": activity, "focus": []}},
    }


class RawImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="worktime-raw-")
        self.cfg = load_config()
        self.cfg["_data_dir"] = self.tmp
        self.store = Store(os.path.join(self.tmp, "worktime.db"))

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_import_then_process(self):
        result = import_document(self.store, raw_doc())
        self.assertEqual(result["days"], 1)
        self.assertEqual(result["activity"], 4)
        self.assertEqual(self.store.count_raw_day(DATE), 4)
        processed = process_date(self.store, self.cfg, DATE, use_llm=False)
        self.assertGreater(processed["segments"], 0)
        apps = {s["app"] for s in self.store.list_segments(DATE)}
        self.assertIn("微信", apps)
        self.assertIn("Excel", apps)

    def test_import_requires_valid_format(self):
        with self.assertRaises(RawFormatError):
            import_document(self.store, {"format": "something-else"})
        with self.assertRaises(RawFormatError):
            import_document(self.store, {"format": "worktime-raw", "version": 1,
                                         "days": {}})
        with self.assertRaises(RawFormatError):
            import_document(self.store, raw_doc(rows=[("bad-time", "A", "a")]))

    def test_reimport_replaces_the_day(self):
        import_document(self.store, raw_doc())
        self.assertEqual(self.store.count_raw_day(DATE), 4)
        import_document(self.store, raw_doc(rows=[("09:00:00", "微信", "com.tencent.mm")]))
        self.assertEqual(self.store.count_raw_day(DATE), 1)
        import_document(self.store, raw_doc(), replace=False)
        self.assertEqual(self.store.count_raw_day(DATE), 5)

    def test_import_from_file(self):
        path = os.path.join(self.tmp, "raw.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(raw_doc(), fh, ensure_ascii=False)
        result = import_file(self.store, path)
        self.assertEqual(result["activity"], 4)
        self.assertTrue(validate_document(raw_doc()))


if __name__ == "__main__":
    unittest.main()
