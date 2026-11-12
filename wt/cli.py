"""Command line entry points."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta

from .config import data_paths, load_config
from .pipeline import process_date
from .report import write_period_report, write_report
from .store import Store
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
            f"llm={'yes' if result.get('llm') else 'no'}"
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
