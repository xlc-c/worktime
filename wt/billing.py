"""Billable time: rates per matter, rounded hours, and invoice exports.

Matters are named ``Client / Project / Sub-task``. A rate set on ``Client``
applies to every child unless the child overrides it, so a consultant sets a
handful of rates instead of one per task.

Everything here is pure standard library and operates on plain segment dicts,
so it is unit-tested without a database or Windows.
"""

from __future__ import annotations

from collections import Counter

from .util import fmt_duration

SEP = " / "


def matter_chain(path: str) -> list[str]:
    """``A / B / C`` -> ``[A / B / C, A / B, A]`` (most specific first)."""
    parts = [p.strip() for p in str(path or "").split("/") if p.strip()]
    out = []
    for idx in range(len(parts), 0, -1):
        out.append(SEP.join(parts[:idx]))
    return out or [""]


def effective_rate(path: str, rates: dict[str, dict]) -> dict:
    """Nearest ancestor with a rate wins."""
    for candidate in matter_chain(path):
        entry = rates.get(candidate)
        if entry and float(entry.get("rate") or 0) > 0:
            return entry
    return {}


def round_hours(hours: float, round_minutes: int) -> float:
    if round_minutes and round_minutes > 0:
        step = round_minutes / 60.0
        return round(round(hours / step) * step, 2)
    return round(hours, 3)


def build_invoice(segments: list[dict], rates: dict[str, dict],
                  currency: str = "CNY", round_minutes: int = 0) -> dict:
    seconds: Counter = Counter()
    tasks: dict[str, Counter] = {}
    for seg in segments:
        matter = seg.get("final_matter") or seg.get("auto_matter") or "未归类"
        seconds[matter] += float(seg.get("duration_s") or 0)
        tasks.setdefault(matter, Counter())[
            seg.get("final_task") or seg.get("auto_task") or ""
        ] += float(seg.get("duration_s") or 0)

    rows = []
    total_amount = 0.0
    total_hours = 0.0
    for matter, sec in seconds.most_common():
        entry = effective_rate(matter, rates)
        rate = float(entry.get("rate") or 0)
        billable = bool(entry.get("billable", 1)) and rate > 0
        hours = round_hours(sec / 3600.0, round_minutes)
        amount = round(hours * rate, 2) if billable else 0.0
        if billable:
            total_amount += amount
            total_hours += hours
        rows.append({
            "matter": matter,
            "seconds": sec,
            "hours": hours,
            "rate": rate,
            "currency": entry.get("currency") or currency,
            "billable": billable,
            "amount": amount,
            "tasks": [t for t, _ in tasks[matter].most_common(3) if t],
        })
    return {
        "rows": rows,
        "total_hours": round(total_hours, 2),
        "total_amount": round(total_amount, 2),
        "currency": currency,
        "unbilled_seconds": sum(r["seconds"] for r in rows if not r["billable"]),
    }


def render_invoice_markdown(invoice: dict, start: str, end: str) -> str:
    title = start if start == end else f"{start} ~ {end}"
    lines = [f"# 工时与费用 {title}", ""]
    lines.append(f"- **计费工时**：{invoice['total_hours']:.2f} 小时")
    lines.append(f"- **合计金额**：{invoice['total_amount']:.2f} {invoice['currency']}")
    lines.append(f"- **非计费用时**：{fmt_duration(invoice['unbilled_seconds'])}")
    lines.append("")
    lines.append("| 事项 | 工时(h) | 单价 | 金额 | 状态 | 主要任务 |")
    lines.append("| --- | ---: | ---: | ---: | --- | --- |")
    for row in invoice["rows"]:
        status = "计费" if row["billable"] else "不计费"
        lines.append(
            f"| {row['matter']} | {row['hours']:.2f} | {row['rate']:.2f} |"
            f" {row['amount']:.2f} | {status} | {'；'.join(row['tasks'])} |"
        )
    lines.append("")
    lines.append("> 单价来自本地「事项费率」设置；未设单价的事项按不计费处理，不会从任何服务器取价。")
    return "\n".join(lines)


def invoice_csv_rows(invoice: dict, start: str, end: str) -> list[list]:
    header = ["start", "end", "matter", "hours", "rate", "currency",
              "billable", "amount", "tasks"]
    rows = [header]
    for row in invoice["rows"]:
        rows.append([
            start, end, row["matter"], f"{row['hours']:.2f}", f"{row['rate']:.2f}",
            row["currency"], 1 if row["billable"] else 0, f"{row['amount']:.2f}",
            "；".join(row["tasks"]),
        ])
    return rows


def write_invoice(store, cfg: dict, date: str, period: str = "day") -> dict:
    from .config import data_paths
    from .report import period_range

    start, end = period_range(date, period)
    segments = store.fetch_segments_between(start, end)
    if not segments:
        return {"written": False, "reason": "no segments", "start": start, "end": end}
    rates = store.matter_rates()
    round_minutes = int((cfg.get("report") or {}).get("round_minutes") or 0)
    invoice = build_invoice(segments, rates,
                            currency=str((cfg.get("report") or {}).get("currency") or "CNY"),
                            round_minutes=round_minutes)
    paths = data_paths(cfg)
    md = render_invoice_markdown(invoice, start, end)
    md_path = paths["reports"] / f"{end}-invoice.md"
    md_path.write_text(md, encoding="utf-8")
    import csv

    csv_path = paths["exports"] / f"{end}-invoice.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerows(invoice_csv_rows(invoice, start, end))
    return {
        "written": True, "start": start, "end": end,
        "markdown": str(md_path), "csv": str(csv_path),
        "total_hours": invoice["total_hours"],
        "total_amount": invoice["total_amount"],
        "currency": invoice["currency"],
    }
