"""Command line entry points."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta

from .billing import write_invoice
from .config import data_paths, load_config
from .pipeline import process_date
from .report import write_period_report, write_report
from .rules import preview_rule
from .store import Store
from .sync import (export_to_file, import_file, preview, pull_folder,
                   push_folder, status)
from .util import shift_date, today_str

log = logging.getLogger("worktime.cli")


def _store(cfg: dict) -> Store:
    return Store(data_paths(cfg)["db"])


def cmd_collect(args) -> int:
    from .collector import main as collector_main

    collector_main()
    return 0


def cmd_process(args) -> int:
    cfg = load_config()
    store = _store(cfg)
    date = args.date or today_str()
    dates = [shift_date(date, -i) for i in range(max(1, args.days))]
    dates.reverse()
    for day in dates:
        result = process_date(store, cfg, day, use_llm=not args.no_llm)
        print(
            f"{day}: segments={result['segments']} "
            f"active={result['active_s'] / 3600:.2f}h "
            f"llm={'yes' if result.get('llm') else 'no'} "
            f"rules={result.get('rules_hit', 0)}"
        )
        if not args.no_report and result["segments"]:
            out = write_report(store, cfg, day)
            if out.get("written"):
                print(f"  report: {out['markdown']}")
                if out.get("xlsx"):
                    print(f"  xlsx:   {out['xlsx']}")
    store.close()
    return 0


def cmd_report(args) -> int:
    cfg = load_config()
    store = _store(cfg)
    date = args.date or today_str()
    period = getattr(args, "period", "day") or "day"
    if period == "day":
        if not store.list_segments(date):
            print(f"{date} 还没有处理过的数据，请先运行 process")
            return 1
        out = write_report(store, cfg, date)
    else:
        out = write_period_report(store, cfg, date, period)
        if not out.get("written"):
            print(f"{date} 附近没有处理过的数据（{out.get('start')} ~ {out.get('end')}）")
            store.close()
            return 1
    print(out)
    store.close()
    return 0


def cmd_simulate(args) -> int:
    from .simulate import simulate_day, simulate_days

    cfg = load_config()
    store = _store(cfg)
    today = today_str()
    end = args.date or shift_date(today, -1)
    days = max(1, args.days)
    dates = [shift_date(end, -(days - 1 - i)) for i in range(days)]
    if today in dates and not args.force:
        print(f"拒绝覆盖今天({today})的真实采集数据；请换一个更早的 --date，"
              f"或加 --force 强制覆盖。")
        store.close()
        return 1
    if len(dates) == 1:
        info = simulate_day(store, cfg, dates[0], reset=not args.keep)
    else:
        info = simulate_days(store, cfg, dates, seed=args.seed)
    print(info)
    print("提示：生成后运行  wt.cli process --days N --date " + dates[-1] + "  生成时间线")
    store.close()
    return 0


def cmd_clean(args) -> int:
    cfg = load_config()
    paths = data_paths(cfg)
    store = _store(cfg)
    end = args.date or today_str()
    days = max(1, args.days)
    dates = [shift_date(end, -(days - 1 - i)) for i in range(days)]
    for date in dates:
        store.delete_day(date)
        for path in (
            paths["reports"] / f"{date}.md",
            paths["exports"] / f"{date}.csv",
            paths["exports"] / f"{date}.xlsx",
        ):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
    print("已删除日期:", ", ".join(dates))
    store.close()
    return 0


def cmd_review(args) -> int:
    from .review import serve

    cfg = load_config()
    serve(cfg, args.date or today_str())
    return 0


def cmd_status(args) -> int:
    cfg = load_config()
    store = _store(cfg)
    print("data dir:", cfg["_data_dir"])
    print("counts:", store.stats())
    store.close()
    return 0


def cmd_prune(args) -> int:
    cfg = load_config()
    store = _store(cfg)
    deleted = store.prune(
        int(cfg["privacy"]["retention_days"]),
        int(cfg["privacy"]["store_raw_clipboard_days"]),
    )
    print("pruned:", deleted)
    store.close()
    return 0


# -- rules -------------------------------------------------------------
def cmd_rules(args) -> int:
    cfg = load_config()
    store = _store(cfg)
    action = args.action
    if action == "list":
        rules = store.list_rules()
        if not rules:
            print("还没有规则。用 wt rules add 或复核页「⚙ 设置 → 规则」添加。")
        for rule in rules:
            conds = " ".join(
                f"{label}={rule[key]}"
                for key, label in (("app", "app"), ("title", "title"),
                                   ("url_domain", "url"), ("focused", "focus"))
                if rule.get(key)
            )
            state = "on " if rule.get("enabled") else "off"
            print(f"[{rule['id']:>3}] {state} p{rule.get('priority', 100):<4}"
                  f" {rule.get('name', ''):<24} {conds}"
                  f" -> {rule.get('matter', '') or '-'} / {rule.get('task', '') or '-'}"
                  f"  (hits {rule.get('matches', 0)})")
    elif action == "add":
        rule = store.upsert_rule({
            "name": args.name,
            "priority": args.priority,
            "app": args.app,
            "title": args.title,
            "url_domain": args.domain,
            "focused": args.focused,
            "matter": args.matter,
            "task": args.task,
            "enabled": not args.disabled,
        })
        print("已添加规则:", rule)
    elif action == "rm":
        store.delete_rule(int(args.id))
        print("已删除规则", args.id)
    elif action == "test":
        date = args.date or today_str()
        segments = store.list_segments(date)
        if not segments:
            print(f"{date} 还没有时间线，先运行 process")
            store.close()
            return 1
        rules = store.list_rules(only_enabled=True)
        if not rules:
            print("没有启用的规则")
        for rule in rules:
            result = preview_rule(rule, segments)
            print(f"[{rule['id']}] {rule.get('name', '')}: 命中 {result['count']} 段"
                  f" / {result['seconds'] / 3600:.2f}h")
            for sample in result["samples"][:3]:
                print(f"    {sample['start']}-{sample['end']} {sample['app']} {sample['title']}")
    store.close()
    return 0


# -- matters / billing -------------------------------------------------
def cmd_matter(args) -> int:
    cfg = load_config()
    store = _store(cfg)
    if args.action in ("list", "ls"):
        matters = store.list_matters()
        if not matters:
            print("还没有设置事项费率。用 wt matter set --path \"客户A / 项目B\" --rate 800")
        for matter in matters:
            print(f"{matter['path']:<40} {matter['rate']:>8.2f} {matter['currency']}"
                  f" {'计费' if matter.get('billable') else '不计费'}")
    elif args.action == "set":
        matter = store.upsert_matter(
            args.path, rate=args.rate, currency=args.currency,
            billable=(None if args.billable is None else args.billable),
            note=args.note,
        )
        print("已更新:", matter)
    store.close()
    return 0


def cmd_invoice(args) -> int:
    cfg = load_config()
    store = _store(cfg)
    date = args.date or today_str()
    out = write_invoice(store, cfg, date, args.period)
    print(out)
    store.close()
    return 0 if out.get("written") else 1


# -- sync --------------------------------------------------------------
def cmd_sync(args) -> int:
    cfg = load_config()
    store = _store(cfg)
    action = args.action
    passphrase = args.passphrase or os.environ.get("WT_SYNC_PASSPHRASE") or ""
    if action == "status":
        print(status(store, cfg))
    elif action == "preview":
        print(preview(store, cfg, days=args.days))
    elif action == "export":
        out = export_to_file(store, cfg, days=args.days, out_dir=args.out,
                             passphrase=passphrase or None)
        print("已导出:", out)
    elif action == "import":
        try:
            print(import_file(store, cfg, args.file, passphrase or None))
        except ValueError as exc:
            print("导入失败:", exc)
            store.close()
            return 1
    elif action == "push":
        try:
            print("已推到同步文件夹:", push_folder(store, cfg, days=args.days,
                                                 passphrase=passphrase or None))
        except ValueError as exc:
            print("导出失败:", exc)
            store.close()
            return 1
    elif action == "pull":
        try:
            print("已从同步文件夹导入:", pull_folder(store, cfg, passphrase or None))
        except ValueError as exc:
            print("导入失败:", exc)
            store.close()
            return 1
    store.close()
    return 0


def cmd_live(args) -> int:
    cfg = load_config()
    store = _store(cfg)
    print(store.live_state())
    store.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="worktime", description="本地工作时间线")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("collect", help="开始采集活动（前台窗口/剪贴板/焦点文本）")
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("process", help="把采集数据切成时间线并命名")
    p.add_argument("--date", help="YYYY-MM-DD，默认今天")
    p.add_argument("--days", type=int, default=1)
    p.add_argument("--no-llm", action="store_true", help="只用确定性命名")
    p.add_argument("--no-report", action="store_true", help="只处理、不生成报表")
    p.set_defaults(func=cmd_process)

    p = sub.add_parser("report", help="生成日报/周报/月报/年报")
    p.add_argument("--date", help="YYYY-MM-DD，默认今天")
    p.add_argument("--period", choices=["day", "week", "month", "year"],
                   default="day", help="报表周期（默认 day）")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("simulate", help="生成模拟数据（用于测试/演示）")
    p.add_argument("--date", help="最后一天的日期 YYYY-MM-DD，默认昨天")
    p.add_argument("--days", type=int, default=1, help="生成连续多少天（默认 1）")
    p.add_argument("--seed", type=int, default=42, help="随机种子，便于复现")
    p.add_argument("--keep", action="store_true", help="保留已有数据（单天模式）")
    p.add_argument("--force", action="store_true", help="允许覆盖今天的真实数据")
    p.set_defaults(func=cmd_simulate)

    p = sub.add_parser("clean", help="删除某天/某几天的测试数据")
    p.add_argument("--date", help="最后一天 YYYY-MM-DD，默认今天")
    p.add_argument("--days", type=int, default=1)
    p.set_defaults(func=cmd_clean)

    p = sub.add_parser("review", help="启动本地复核页")
    p.add_argument("--date", help="YYYY-MM-DD，默认今天")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("status", help="查看数据目录与记录数")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("prune", help="按保留策略清理旧数据")
    p.set_defaults(func=cmd_prune)

    p = sub.add_parser("live", help="采集器是否在跑（供托盘/脚本调用）")
    p.set_defaults(func=cmd_live)

    p = sub.add_parser("rules", help="自动归类规则：list/add/rm/test")
    p.add_argument("action", choices=["list", "add", "rm", "test"])
    p.add_argument("--name", default="", help="规则名（add）")
    p.add_argument("--app", default="", help="匹配应用名，含 re: 前缀为正则")
    p.add_argument("--title", default="", help="匹配窗口/网页标题")
    p.add_argument("--domain", default="", help="匹配网址/域名")
    p.add_argument("--focused", default="", help="匹配焦点文本")
    p.add_argument("--matter", default="", help="命中后归入的事项")
    p.add_argument("--task", default="", help="命中后的任务名（可留空）")
    p.add_argument("--priority", type=int, default=100, help="越大越先匹配")
    p.add_argument("--disabled", action="store_true", help="添加时先停用")
    p.add_argument("--id", type=int, default=0, help="规则 ID（rm）")
    p.add_argument("--date", help="YYYY-MM-DD（test 用）")
    p.set_defaults(func=cmd_rules)

    p = sub.add_parser("matter", help="事项费率（计费）：list/set")
    p.add_argument("action", choices=["list", "ls", "set"])
    p.add_argument("--path", default="", help="事项路径，如 \"客户A / 项目B\"")
    p.add_argument("--rate", type=float, default=None, help="每小时单价")
    p.add_argument("--currency", default=None, help="币种，默认 CNY")
    p.add_argument("--billable", type=int, default=None, choices=[0, 1])
    p.add_argument("--note", default=None)
    p.set_defaults(func=cmd_matter)

    p = sub.add_parser("invoice", help="生成工时/费用单（Markdown + CSV）")
    p.add_argument("--date", help="YYYY-MM-DD，默认今天")
    p.add_argument("--period", choices=["day", "week", "month", "year"],
                   default="month")
    p.set_defaults(func=cmd_invoice)

    p = sub.add_parser("sync", help="多端同步（默认关闭，逐项选择通道）")
    p.add_argument("action", choices=["status", "preview", "export", "import",
                                      "push", "pull"])
    p.add_argument("--days", type=int, default=7, help="导出最近多少天")
    p.add_argument("--out", help="导出目录（默认 data/exports）")
    p.add_argument("--file", help="要导入的 .wtb 文件")
    p.add_argument("--passphrase", help="加密口令（也可用环境变量 WT_SYNC_PASSPHRASE）")
    p.set_defaults(func=cmd_sync)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
