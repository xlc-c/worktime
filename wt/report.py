"""Reports: daily timeline plus week/month/year aggregates."""

from __future__ import annotations

import csv
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from .config import data_paths
from .util import fmt_clock, fmt_duration, ts_to_dt

log = logging.getLogger("worktime.report")


def period_range(date_str: str, period: str) -> tuple[str, str]:
    """Return inclusive [start_date, end_date] for day/week/month/year."""
    day = datetime.strptime(date_str, "%Y-%m-%d")
    if period == "week":
        start = day - timedelta(days=day.weekday())
        end = start + timedelta(days=6)
    elif period == "month":
        start = day.replace(day=1)
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    elif period == "year":
        start = day.replace(month=1, day=1)
        end = day.replace(month=12, day=31)
    else:
        start = end = day
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def summarize_period(segments: list[dict], cfg: dict) -> dict:
    if not segments:
        return {
            "active_s": 0.0, "days": 0, "avg_s": 0.0, "coverage": 0.0,
            "avg_conf": 0.0, "by_matter": [], "by_app": [], "by_task": [],
            "by_day": [], "by_month": [],
        }
    active = sum(s.get("duration_s", 0.0) for s in segments)
    dates = sorted({s["date"] for s in segments})
    day_seconds: Counter = Counter()
    day_top: dict[str, Counter] = defaultdict(Counter)
    matter_seconds: Counter = Counter()
    matter_tasks: dict[str, Counter] = defaultdict(Counter)
    app_seconds: Counter = Counter()
    task_seconds: Counter = Counter()
    month_seconds: Counter = Counter()
    for seg in segments:
        matter = seg.get("final_matter") or seg.get("auto_matter") or "未归类"
        task = seg.get("final_task") or seg.get("auto_task") or "未归类"
        duration = seg.get("duration_s", 0.0)
        date = seg["date"]
        day_seconds[date] += duration
        day_top[date][matter] += duration
        matter_seconds[matter] += duration
        matter_tasks[matter][task] += duration
        app_seconds[seg.get("app") or "unknown"] += duration
        task_seconds[task] += duration
        month_seconds[date[:7]] += duration
    workday = float(cfg.get("report", {}).get("workday_hours", 8.0)) * 3600
    by_day = []
    for date in sorted(day_seconds):
        top = day_top[date].most_common(1)
        by_day.append({
            "date": date,
            "seconds": day_seconds[date],
            "top": top[0][0] if top else "—",
        })
    by_month = [
        {"month": month, "seconds": seconds}
        for month, seconds in sorted(month_seconds.items())
    ]
    confs = [float(s.get("confidence") or 0) for s in segments if s.get("confidence")]
    return {
        "active_s": active,
        "days": len(dates),
        "avg_s": active / max(1, len(dates)),
        "coverage": active / (workday * max(1, len(dates))) if workday else 0.0,
        "avg_conf": sum(confs) / len(confs) if confs else 0.0,
        "by_matter": [
            {"matter": matter, "seconds": seconds,
             "ratio": seconds / active if active else 0.0,
             "tasks": [t for t, _ in matter_tasks[matter].most_common(4)]}
            for matter, seconds in matter_seconds.most_common()
        ],
        "by_app": [
            {"app": app, "seconds": seconds,
             "ratio": seconds / active if active else 0.0}
            for app, seconds in app_seconds.most_common()
        ],
        "by_task": [
            {"task": task, "seconds": seconds}
            for task, seconds in task_seconds.most_common(20)
        ],
        "by_day": by_day,
        "by_month": by_month,
    }


def render_period_markdown(segments: list[dict], cfg: dict, period: str,
                           start_date: str, end_date: str) -> str:
    summary = summarize_period(segments, cfg)
    label = {"week": "周报", "month": "月报", "year": "年报"}.get(period, "日报")
    title = start_date if start_date == end_date else f"{start_date} ~ {end_date}"
    lines: list[str] = []
    lines.append(f"# {title} {label}")
    lines.append("")
    lines.append(f"- **统计范围**：{start_date} 至 {end_date}（有数据 {summary['days']} 天）")
    lines.append(
        f"- **活跃时间**：{fmt_duration(summary['active_s'])}"
        f"（日均 {fmt_duration(summary['avg_s'])}，"
        f"覆盖工作日 {summary['coverage'] * 100:.0f}%）"
    )
    lines.append(f"- **平均置信度**：{summary['avg_conf']:.2f}")
    lines.append("")

    lines.append("## 按事项")
    lines.append("")
    lines.append("| 事项 | 用时 | 占比 | 主要任务 |")
    lines.append("| --- | ---: | ---: | --- |")
    for item in summary["by_matter"]:
        lines.append(
            f"| {item['matter']} | {fmt_duration(item['seconds'])} |"
            f" {item['ratio'] * 100:.0f}% | {'；'.join(item['tasks'])} |"
        )
    lines.append("")

    lines.append("## 按应用")
    lines.append("")
    lines.append("| 应用 | 用时 | 占比 |")
    lines.append("| --- | ---: | ---: |")
    for item in summary["by_app"]:
        lines.append(
            f"| {item['app']} | {fmt_duration(item['seconds'])} |"
            f" {item['ratio'] * 100:.0f}% |"
        )
    lines.append("")

    lines.append("## 主要任务")
    lines.append("")
    lines.append("| 任务 | 用时 |")
    lines.append("| --- | ---: |")
    for item in summary["by_task"][:15]:
        lines.append(f"| {item['task']} | {fmt_duration(item['seconds'])} |")
    lines.append("")

    if period == "year":
        lines.append("## 按月")
        lines.append("")
        lines.append("| 月份 | 活跃 |")
        lines.append("| --- | ---: |")
        for item in summary["by_month"]:
            lines.append(f"| {item['month']} | {fmt_duration(item['seconds'])} |")
        lines.append("")

    lines.append("## 按天")
    lines.append("")
    lines.append("| 日期 | 活跃 | 主要事项 |")
    lines.append("| --- | ---: | --- |")
    for item in summary["by_day"]:
        lines.append(
            f"| {item['date']} | {fmt_duration(item['seconds'])} | {item['top']} |"
        )
    lines.append("")
    lines.append("> 数据来自本机采集；导出内容不含剪贴板/输入原文。")
    return "\n".join(lines)


def write_period_report(store, cfg: dict, date: str, period: str) -> dict:
    start_date, end_date = period_range(date, period)
    segments = store.fetch_segments_between(start_date, end_date)
    if not segments:
        return {"period": period, "written": False, "reason": "no segments",
                "start": start_date, "end": end_date}
    paths = data_paths(cfg)
    markdown = render_period_markdown(segments, cfg, period, start_date, end_date)
    label = period if period in ("week", "month", "year") else "day"
    out = paths["reports"] / f"{end_date}-{label}.md"
    out.write_text(markdown, encoding="utf-8")
    csv_path = paths["exports"] / f"{end_date}-{label}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["date", "start", "end", "minutes", "app", "task",
                         "matter", "confidence", "title"])
        for seg in segments:
            writer.writerow([
                seg["date"], seg["start_ts"], seg["end_ts"],
                round(seg.get("duration_s", 0) / 60.0, 2),
                seg.get("app", ""),
                seg.get("final_task") or seg.get("auto_task") or "",
                seg.get("final_matter") or seg.get("auto_matter") or "",
                seg.get("confidence") or 0,
                seg.get("title", ""),
            ])
    return {
        "period": period,
        "written": True,
        "start": start_date,
        "end": end_date,
        "days": len({s["date"] for s in segments}),
        "active_s": sum(s.get("duration_s", 0) for s in segments),
        "markdown": str(out),
        "csv": str(csv_path),
    }


def summarize(segments: list[dict], cfg: dict) -> dict:
    if not segments:
        return {
            "active_s": 0.0,
            "span_s": 0.0,
            "away_s": 0.0,
            "coverage": 0.0,
            "avg_conf": 0.0,
            "by_matter": [],
            "by_app": [],
            "by_task": [],
        }
    active = sum(s.get("duration_s", 0.0) for s in segments)
    first = min(s["start_ts"] for s in segments)
    last = max(s["end_ts"] for s in segments)
    span = (ts_to_dt(last) - ts_to_dt(first)).total_seconds()
    away = max(0.0, span - active)
    workday = float(cfg.get("report", {}).get("workday_hours", 8.0)) * 3600

    matter_seconds: Counter = Counter()
    matter_tasks: dict[str, Counter] = defaultdict(Counter)
    app_seconds: Counter = Counter()
    task_seconds: Counter = Counter()
    for seg in segments:
        matter = seg.get("final_matter") or seg.get("auto_matter") or "未归类"
        task = seg.get("final_task") or seg.get("auto_task") or "未归类"
        duration = seg.get("duration_s", 0.0)
        matter_seconds[matter] += duration
        matter_tasks[matter][task] += duration
        app_seconds[seg.get("app") or "unknown"] += duration
        task_seconds[task] += duration

    by_matter = [
        {
            "matter": matter,
            "seconds": seconds,
            "ratio": (seconds / active) if active else 0.0,
            "tasks": [t for t, _ in matter_tasks[matter].most_common(4)],
        }
        for matter, seconds in matter_seconds.most_common()
    ]
    by_app = [
        {"app": app, "seconds": seconds, "ratio": (seconds / active) if active else 0.0}
        for app, seconds in app_seconds.most_common()
    ]
    by_task = [
        {"task": task, "seconds": seconds}
        for task, seconds in task_seconds.most_common(20)
    ]
    confs = [float(s.get("confidence") or 0) for s in segments if s.get("confidence")]
    return {
        "active_s": active,
        "span_s": span,
        "away_s": away,
        "coverage": (active / workday) if workday else 0.0,
        "avg_conf": sum(confs) / len(confs) if confs else 0.0,
        "by_matter": by_matter,
        "by_app": by_app,
        "by_task": by_task,
    }


def render_markdown(date: str, segments: list[dict], cfg: dict) -> str:
    summary = summarize(segments, cfg)
    lines: list[str] = []
    lines.append(f"# {date} 工作时间线")
    lines.append("")
    lines.append(
        f"- **活跃时间**：{fmt_duration(summary['active_s'])}"
        f"（占 8 小时工作日 {summary['coverage'] * 100:.0f}%）"
    )
    lines.append(
        f"- **时间跨度**：{fmt_duration(summary['span_s'])}"
        f"，其中离开/空闲约 {fmt_duration(summary['away_s'])}"
    )
    lines.append(f"- **分段数**：{len(segments)}，自动命名平均置信度 {summary['avg_conf']:.2f}")
    lines.append("- **数据来源**：本机采集（窗口/网页/剪贴板/焦点文本），未上传任何服务器")
    lines.append("")

    lines.append("## 按事项汇总")
    lines.append("")
    lines.append("| 事项 | 用时 | 占比 | 主要任务 |")
    lines.append("| --- | ---: | ---: | --- |")
    for item in summary["by_matter"]:
        tasks = "；".join(item["tasks"])
        lines.append(
            f"| {item['matter']} | {fmt_duration(item['seconds'])} |"
            f" {item['ratio'] * 100:.0f}% | {tasks} |"
        )
    if not summary["by_matter"]:
        lines.append("| — | — | — | — |")
    lines.append("")

    lines.append("## 时间线")
    lines.append("")
    lines.append("| 开始 | 结束 | 时长 | 应用 | 任务 | 事项 | 置信度 | 窗口/网页 |")
    lines.append("| --- | --- | ---: | --- | --- | --- | ---: | --- |")
    for seg in segments:
        context = seg.get("page_title") or seg.get("title") or ""
        context = context.replace("|", "/")[:60]
        lines.append(
            f"| {fmt_clock(seg['start_ts'])} | {fmt_clock(seg['end_ts'])} |"
            f" {fmt_duration(seg.get('duration_s', 0))} | {seg.get('app', '')} |"
            f" {seg.get('final_task') or seg.get('auto_task') or ''} |"
            f" {seg.get('final_matter') or seg.get('auto_matter') or ''} |"
            f" {float(seg.get('confidence') or 0):.2f} | {context} |"
        )
    lines.append("")
    lines.append("## 按应用")
    lines.append("")
    lines.append("| 应用 | 用时 | 占比 |")
    lines.append("| --- | ---: | ---: |")
    for item in summary["by_app"]:
        lines.append(
            f"| {item['app']} | {fmt_duration(item['seconds'])} | {item['ratio'] * 100:.0f}% |"
        )
    lines.append("")
    lines.append(
        "> 提示：把 `未归类` 的事项在复核页里改一次，之后同类活动会自动沿用；"
        "每天复核约 3–5 分钟即可把准确率稳定在 80% 以上。"
    )
    return "\n".join(lines)


def write_csv(path: Path, date: str, segments: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "date", "start", "end", "minutes", "app", "task", "matter",
            "confidence", "title", "url",
        ])
        for seg in segments:
            writer.writerow([
                date,
                seg["start_ts"],
                seg["end_ts"],
                round(seg.get("duration_s", 0) / 60.0, 2),
                seg.get("app", ""),
                seg.get("final_task") or seg.get("auto_task") or "",
                seg.get("final_matter") or seg.get("auto_matter") or "",
                seg.get("confidence") or 0,
                seg.get("title", ""),
                seg.get("url", ""),
            ])


def write_xlsx(path: Path, date: str, segments: list[dict], cfg: dict) -> bool:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except Exception:
        return False
    summary = summarize(segments, cfg)
    wb = Workbook()
    ws = wb.active
    ws.title = "汇总"
    ws["A1"] = f"{date} 工作时间统计"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "活跃时间"
    ws["B2"] = fmt_duration(summary["active_s"])
    ws["A3"] = "时间跨度"
    ws["B3"] = fmt_duration(summary["span_s"])
    ws["A4"] = "离开/空闲"
    ws["B4"] = fmt_duration(summary["away_s"])
    ws["A5"] = "占 8 小时"
    ws["B5"] = f"{summary['coverage'] * 100:.0f}%"

    header_fill = PatternFill("solid", fgColor="DDEBF7")
    row = 7
    ws.cell(row=row, column=1, value="事项").font = Font(bold=True)
    ws.cell(row=row, column=2, value="用时").font = Font(bold=True)
    ws.cell(row=row, column=3, value="占比").font = Font(bold=True)
    ws.cell(row=row, column=4, value="主要任务").font = Font(bold=True)
    for col in range(1, 5):
        ws.cell(row=row, column=col).fill = header_fill
    for item in summary["by_matter"]:
        row += 1
        ws.cell(row=row, column=1, value=item["matter"])
        ws.cell(row=row, column=2, value=fmt_duration(item["seconds"]))
        ws.cell(row=row, column=3, value=f"{item['ratio'] * 100:.0f}%")
        ws.cell(row=row, column=4, value="；".join(item["tasks"]))
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 10
    ws.column_dimensions["D"].width = 60

    ws2 = wb.create_sheet("时间线")
    headers = ["开始", "结束", "分钟", "应用", "任务", "事项", "置信度", "窗口/网页"]
    for col, title in enumerate(headers, start=1):
        cell = ws2.cell(row=1, column=col, value=title)
        cell.font = Font(bold=True)
        cell.fill = header_fill
    for i, seg in enumerate(segments, start=2):
        ws2.cell(row=i, column=1, value=fmt_clock(seg["start_ts"]))
        ws2.cell(row=i, column=2, value=fmt_clock(seg["end_ts"]))
        ws2.cell(row=i, column=3, value=round(seg.get("duration_s", 0) / 60.0, 1))
        ws2.cell(row=i, column=4, value=seg.get("app", ""))
        ws2.cell(row=i, column=5, value=seg.get("final_task") or seg.get("auto_task") or "")
        ws2.cell(row=i, column=6, value=seg.get("final_matter") or seg.get("auto_matter") or "")
        ws2.cell(row=i, column=7, value=seg.get("confidence") or 0)
        ws2.cell(row=i, column=8, value=seg.get("page_title") or seg.get("title") or "")
    widths = [8, 8, 8, 10, 26, 20, 8, 60]
    for idx, width in enumerate(widths, start=1):
        ws2.column_dimensions[chr(64 + idx)].width = width
    for row_cells in ws2.iter_rows(min_row=2, max_col=8):
        for cell in row_cells:
            cell.alignment = Alignment(vertical="top", wrap_text=False)
    wb.save(path)
    return True


def write_report(store, cfg: dict, date: str) -> dict:
    paths = data_paths(cfg)
    segments = store.list_segments(date)
    if not segments:
        return {"date": date, "written": False, "reason": "no segments"}
    markdown = render_markdown(date, segments, cfg)
    md_path = paths["reports"] / f"{date}.md"
    md_path.write_text(markdown, encoding="utf-8")
    csv_path = paths["exports"] / f"{date}.csv"
    write_csv(csv_path, date, segments)
    result = {
        "date": date,
        "written": True,
        "segments": len(segments),
        "markdown": str(md_path),
        "csv": str(csv_path),
    }
    if cfg.get("report", {}).get("xlsx", True):
        xlsx_path = paths["exports"] / f"{date}.xlsx"
        if write_xlsx(xlsx_path, date, segments, cfg):
            result["xlsx"] = str(xlsx_path)
    return result
