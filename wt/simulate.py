"""Generate realistic synthetic days so the pipeline/UI can be tested or
demoed without waiting for real capture. Only used by `wt.cli simulate`."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from .store import Store
from .util import clip_preview, hash_text

PROC = {
    "Excel": "excel.exe",
    "Outlook": "outlook.exe",
    "Lync": "lync.exe",
    "Chrome": "chrome.exe",
    "Edge": "msedge.exe",
    "Notepad": "notepad.exe",
}

BLOCKS = [
    # start, end, app, title, url, page_title, page_text, focus
    ("09:00", "09:20", "Excel", "P2401_成本测算.xlsx - Excel", None, None, None,
     "B12 单价 12.34 数量 1000"),
    ("09:20", "09:35", "Edge", "供应商报价单 Q-8891 - Microsoft Edge",
     "https://supplier.example.com/quote/Q-8891", "供应商报价单 Q-8891",
     "供应商：华东贸易 报价单号 Q-8891 单价 12.34", None),
    ("09:35", "10:00", "Excel", "P2401_成本测算.xlsx - Excel", None, None, None,
     "成本合计 12,345.67"),
    ("10:00", "10:20", "Outlook", "收件箱 - zhangsan@company.com - Outlook", None, None, None,
     "主题：华东贸易对账 20241112"),
    ("10:20", "10:29", "Lync", "与张三的对话 - Skype for Business", None, None, None,
     "张三：订单 20241112-0032 请核对"),
    ("10:29", "10:30", "Notepad", "临时.txt - Notepad", None, None, None,
     "随手记：12345.67"),
    ("10:30", "11:05", "Edge", "订单 20241112-0032 - ERP",
     "https://erp.example.com/order/20241112-0032", "订单 20241112-0032",
     "客户：华东贸易 订单号 20241112-0032 金额 12345.67", None),
    # 11:05-11:30 away
    ("11:30", "12:00", "Excel", "P2402_回款台账.xlsx - Excel", None, None, None,
     "客户华东贸易 回款 12,345.67"),
    # 12:00-13:30 lunch away
    ("13:30", "13:50", "Chrome", "Re: 华东贸易对账 - 邮箱",
     "https://mail.example.com/thread/778", "Re: 华东贸易对账 - 邮箱",
     "请核对 20241112-0032 订单金额 12345.67", None),
    # short Lync interruption in the middle of reading the same email thread
    ("13:50", "13:52", "Lync", "与王五的对话 - Skype for Business", None, None, None,
     "王五：这个报价单 Q-8892 有更新"),
    ("13:52", "14:00", "Chrome", "Re: 华东贸易对账 - 邮箱",
     "https://mail.example.com/thread/778", "Re: 华东贸易对账 - 邮箱",
     "请核对 20241112-0032 订单金额 12345.67", None),
    ("14:00", "14:15", "Lync", "与李四的对话 - Skype for Business", None, None, None,
     "李四：发票 P2403 已开 请查收"),
    ("14:15", "14:45", "Excel", "P2403_发票清单.xlsx - Excel", None, None, None,
     "发票号 20241112-0032 金额 12345.67"),
    ("14:45", "15:15", "Edge", "银行流水查询 - 网上银行",
     "https://bank.example.com/flow", "银行流水查询",
     "20241112 流水 20241112-0032 收入 12345.67", None),
    ("15:15", "15:40", "Lync", "与张三的对话 - Skype for Business", None, None, None,
     "张三：下周一前把 P2401 成本表发我"),
    ("15:40", "16:10", "Excel", "P2402_回款台账.xlsx - Excel", None, None, None,
     "回款合计 123,456.00"),
    ("16:10", "16:30", "Outlook", "收件箱 - zhangsan@company.com - Outlook", None, None, None,
     "主题：发票 P2403 确认"),
    ("16:30", "17:00", "Chrome", "供应商报价单 Q-8892 - Google Chrome",
     "https://supplier.example.com/quote/Q-8892", "供应商报价单 Q-8892",
     "供应商：华南物资 报价单号 Q-8892 单价 11.80", None),
]

CLIPBOARD = [
    ("09:32", "Edge", "供应商报价单 Q-8891 - Microsoft Edge",
     "供应商报价 Q-8891 单价 12.34 数量 1000"),
    ("09:36", "Excel", "P2401_成本测算.xlsx - Excel",
     "供应商报价 Q-8891 单价 12.34 数量 1000"),
    ("13:35", "Chrome", "Re: 华东贸易对账 - 邮箱",
     "请核对 20241112-0032 订单金额 12345.67"),
    ("14:02", "Lync", "与李四的对话 - Skype for Business",
     "请核对 20241112-0032 订单金额 12345.67"),
    ("14:10", "Lync", "与李四的对话 - Skype for Business",
     "发票号 20241112-0032 金额 12345.67"),
    ("14:16", "Excel", "P2403_发票清单.xlsx - Excel",
     "发票号 20241112-0032 金额 12345.67"),
]

# ---------------------------------------------------------------------------
# Multi-day generator: every day uses a different mix of matters, lengths and
# one or two short interruptions, so charts/timeline look realistic.
# ---------------------------------------------------------------------------

MATTERS = [
    {"excel": "P2401_成本测算.xlsx - Excel", "focus": "B12 单价 12.34 数量 1000",
     "web": {"app": "Edge", "title": "供应商报价单 Q-8891 - Microsoft Edge",
             "url": "https://supplier.example.com/quote/Q-8891",
             "page": "供应商报价单 Q-8891",
             "text": "供应商：华东贸易 报价单号 Q-8891 单价 12.34 数量 1000"}},
    {"excel": "P2402_回款台账.xlsx - Excel", "focus": "客户华东贸易 回款 12,345.67",
     "web": {"app": "Edge", "title": "银行流水查询 - 网上银行",
             "url": "https://bank.example.com/flow", "page": "银行流水查询",
             "text": "20241112 流水 20241112-0032 收入 12345.67"}},
    {"excel": "P2403_发票清单.xlsx - Excel", "focus": "发票号 20241112-0032 金额 12345.67",
     "web": {"app": "Chrome", "title": "电子发票平台 - 发票列表",
             "url": "https://invoice.example.com/list", "page": "电子发票平台",
             "text": "发票号 20241112-0032 状态：已开 金额 12345.67"}},
    {"excel": "订单核对_0032.xlsx - Excel", "focus": "订单号 20241112-0032 金额 12345.67",
     "web": {"app": "Edge", "title": "订单 20241112-0032 - ERP",
             "url": "https://erp.example.com/order/20241112-0032",
             "page": "订单 20241112-0032",
             "text": "客户：华东贸易 订单号 20241112-0032 金额 12345.67"}},
    {"excel": "Q-8892_比价.xlsx - Excel", "focus": "报价 Q-8892 单价 11.80",
     "web": {"app": "Chrome", "title": "供应商报价单 Q-8892 - Google Chrome",
             "url": "https://supplier.example.com/quote/Q-8892",
             "page": "供应商报价单 Q-8892",
             "text": "供应商：华南物资 报价单号 Q-8892 单价 11.80"}},
    {"excel": "P2404_项目预算.xlsx - Excel", "focus": "预算合计 456,789.00",
     "web": {"app": "Edge", "title": "项目预算审批 - OA",
             "url": "https://oa.example.com/budget/P2404", "page": "项目预算审批",
             "text": "项目 P2404 预算 456,789.00 待审批"}},
]

MAIL = ("Outlook", "收件箱 - zhangsan@company.com - Outlook",
        "主题：华东贸易对账 20241112")
MAIL_THREAD = {"app": "Chrome", "title": "Re: 华东贸易对账 - 邮箱",
               "url": "https://mail.example.com/thread/778",
               "page": "Re: 华东贸易对账 - 邮箱",
               "text": "请核对 20241112-0032 订单金额 12345.67"}
LYNC_A = "与张三的对话 - Skype for Business"
LYNC_B = "与李四的对话 - Skype for Business"
LYNC_C = "与王五的对话 - Skype for Business"


def _gen_day(date: str, day_index: int, rng: random.Random) -> dict:
    blocks: list[tuple] = []
    clipboard: list[tuple] = []  # (minute, app, title, text)
    t = 9 * 60 + rng.randint(0, 9)

    def add(duration, app, title, url=None, page=None, text=None, focus_text=None):
        nonlocal t
        blocks.append((t, t + duration, app, title, url, page, text, focus_text))
        t += duration

    def gap(minutes):
        nonlocal t
        t += minutes

    matters = [MATTERS[(day_index * 2 + k) % len(MATTERS)] for k in range(3)]

    def session(matter):
        add(rng.randint(15, 21), "Excel", matter["excel"], focus_text=matter["focus"])
        web_start = t
        add(rng.randint(9, 12), matter["web"]["app"], matter["web"]["title"],
            matter["web"]["url"], matter["web"]["page"], matter["web"]["text"])
        excel_start = t
        add(rng.randint(10, 14), "Excel", matter["excel"], focus_text=matter["focus"])
        clipboard.append((web_start + 2, matter["web"]["app"], matter["web"]["title"],
                          matter["web"]["text"]))
        clipboard.append((excel_start + 2, "Excel", matter["excel"], matter["web"]["text"]))

    # morning: session A, mail interrupted by Lync, sessions B and C
    session(matters[0])
    add(rng.randint(9, 11), MAIL[0], MAIL[1], focus_text=MAIL[2])
    add(2, "Lync", LYNC_C, focus_text="王五：这个报价单 Q-8892 有更新")
    add(rng.randint(9, 12), MAIL[0], MAIL[1], focus_text=MAIL[2])
    gap(rng.randint(12, 18))
    session(matters[1])
    session(matters[2])
    add(rng.randint(7, 9), MAIL_THREAD["app"], MAIL_THREAD["title"],
        MAIL_THREAD["url"], MAIL_THREAD["page"], MAIL_THREAD["text"])
    add(2, "Lync", LYNC_B, focus_text="李四：发票 P2403 已开")
    add(rng.randint(6, 8), MAIL_THREAD["app"], MAIL_THREAD["title"],
        MAIL_THREAD["url"], MAIL_THREAD["page"], MAIL_THREAD["text"])

    # lunch break
    if t < 12 * 60:
        gap(12 * 60 - t)
    gap(90)

    # afternoon: session D, Lync, session E, mail + order, session F, wrap-up
    session(matters[0])
    add(rng.randint(10, 14), "Lync", LYNC_A, focus_text="张三：下周一前把成本表发我")
    session(matters[2])
    add(rng.randint(7, 9), MAIL_THREAD["app"], MAIL_THREAD["title"],
        MAIL_THREAD["url"], MAIL_THREAD["page"], MAIL_THREAD["text"])
    add(rng.randint(6, 9), "Edge", "订单 20241112-0041 - ERP",
        "https://erp.example.com/order/20241112-0041", "订单 20241112-0041",
        "客户：华南物资 订单号 20241112-0041 金额 8,765.00")
    session(matters[1])
    add(rng.randint(7, 9), MAIL[0], MAIL[1], focus_text=MAIL[2])

    base = datetime.strptime(date, "%Y-%m-%d")
    step = timedelta(seconds=10)
    raw_rows, web_rows, focus_rows = [], [], []
    for start, end, app, title, url, page, text, focus_text in blocks:
        cursor = base + timedelta(minutes=start)
        end_dt = base + timedelta(minutes=end)
        while cursor < end_dt:
            ts = cursor.strftime("%Y-%m-%dT%H:%M:%S")
            raw_rows.append((ts, app, PROC.get(app, "unknown"), title, 0, 0.0, "active"))
            if url:
                web_rows.append((ts, app, url, page or title, text or "", "", 0))
            if focus_text:
                focus_rows.append((ts, app, title, focus_text))
            cursor += step

    clip_rows = []
    for minute, app, title, text in clipboard:
        ts = (base + timedelta(minutes=minute)).strftime("%Y-%m-%dT%H:%M:%S")
        clip_rows.append((ts, hash_text(text), clip_preview(text, 240), app, title, len(text)))

    return {
        "raw": raw_rows, "web": web_rows, "focus": focus_rows, "clipboard": clip_rows,
    }


def simulate_days(store: Store, cfg: dict, dates: list[str], seed: int = 42) -> dict:
    """Generate one varied working day per date (weekends are still generated)."""
    result = {"dates": []}
    for index, date in enumerate(dates):
        store.delete_day(date)
        rng = random.Random(seed * 1000 + index)
        data = _gen_day(date, index, rng)
        store.bulk_import(raw=data["raw"], web=data["web"],
                          clip=data["clipboard"], focus=data["focus"])
        result["dates"].append({
            "date": date,
            "raw": len(data["raw"]),
            "web": len(data["web"]),
            "focus": len(data["focus"]),
            "clipboard": len(data["clipboard"]),
        })
    return result


def _dt(date: str, hhmm: str) -> datetime:
    fmt = "%Y-%m-%d %H:%M:%S" if hhmm.count(":") == 2 else "%Y-%m-%d %H:%M"
    return datetime.strptime(f"{date} {hhmm}", fmt)


def simulate_day(store: Store, cfg: dict, date: str, reset: bool = True) -> dict:
    if reset:
        store.delete_day(date)

    raw_rows: list[tuple] = []
    web_rows: list[tuple] = []
    focus_rows: list[tuple] = []
    for start_s, end_s, app, title, url, page_title, page_text, focus_text in BLOCKS:
        start = _dt(date, start_s)
        end = _dt(date, end_s)
        step = timedelta(seconds=10)
        cursor = start
        while cursor < end:
            ts = cursor.strftime("%Y-%m-%dT%H:%M:%S")
            raw_rows.append((ts, app, PROC.get(app, "unknown"), title, 0, 0.0, "active"))
            if url:
                web_rows.append((ts, app, url, page_title or title, page_text or "", "", 0))
            if focus_text:
                focus_rows.append((ts, app, title, focus_text))
            cursor += step

    clip_rows: list[tuple] = []
    for hhmm, app, title, text in CLIPBOARD:
        ts = _dt(date, hhmm).strftime("%Y-%m-%dT%H:%M:%S")
        clip_rows.append((ts, hash_text(text), clip_preview(text, 240), app, title, len(text)))

    store.bulk_import(raw=raw_rows, web=web_rows, clip=clip_rows, focus=focus_rows)
    return {
        "date": date,
        "raw": len(raw_rows),
        "web": len(web_rows),
        "focus": len(focus_rows),
        "clipboard": len(clip_rows),
    }
