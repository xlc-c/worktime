"""Tests for week/month/year aggregate reports."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wt.report import (  # noqa: E402
    period_range,
    render_period_markdown,
    summarize_period,
)


def cfg():
    return {"report": {"workday_hours": 8.0}}


def seg(date, start, end, app="Excel", task="做表", matter="P2401 成本测算"):
    sh, sm = (int(x) for x in start.split(":"))
    eh, em = (int(x) for x in end.split(":"))
    duration = ((eh * 60 + em) - (sh * 60 + sm)) * 60
    return {
        "date": date,
        "start_ts": date + "T" + start + ":00",
        "end_ts": date + "T" + end + ":00",
        "duration_s": float(duration),
        "app": app,
        "final_task": task,
        "final_matter": matter,
        "confidence": 0.8,
        "title": task,
    }


class PeriodReportTests(unittest.TestCase):
    def test_week_range(self):
        start, end = period_range("2026-11-10", "week")  # Tuesday
        self.assertEqual(start, "2026-11-09")
        self.assertEqual(end, "2026-11-15")

    def test_month_range(self):
        start, end = period_range("2026-11-10", "month")
        self.assertEqual(start, "2026-11-01")
        self.assertEqual(end, "2026-11-30")

    def test_year_range(self):
        start, end = period_range("2026-11-10", "year")
        self.assertEqual(start, "2026-01-01")
        self.assertEqual(end, "2026-12-31")

    def test_summary_and_markdown(self):
        segments = [
            seg("2026-11-09", "09:00", "10:00"),
            seg("2026-11-10", "09:00", "11:00", app="Edge", task="查订单", matter="订单 0032"),
        ]
        summary = summarize_period(segments, cfg())
        self.assertEqual(summary["days"], 2)
        self.assertAlmostEqual(summary["active_s"], 3 * 3600)
        markdown = render_period_markdown(segments, cfg(), "week", "2026-11-09", "2026-11-15")
        self.assertIn("周报", markdown)
        self.assertIn("按事项", markdown)
        self.assertIn("P2401 成本测算", markdown)
        self.assertIn("2026-11-10", markdown)


if __name__ == "__main__":
    unittest.main()
