# 跨平台方案（Windows / macOS / Android / 鸿蒙）

先说结论：**能做，而且不需要重写时间线、规则、报表、计费、同步这些核心**。
WorkTime 现在的核心（`wt/segment.py`、`classify.py`、`rules.py`、`billing.py`、`report.py`、`sync.py`）
是纯标准库、零平台依赖的 Python；真正跟操作系统绑定的只有 `wt/winapi.py` + `wt/uia_focus.py` 这两个采集文件。
所以“多平台”= **每个平台只写一个采集器，把原始事件写进同一个契约**，其余全部复用。

## 平台能力矩阵

| 平台 | 能不能跑 | 采集方式 | 关键限制 | 工作量 |
|---|---|---|---|---|
| Windows（已发布） | ✅ | `GetForegroundWindow` + UIA 焦点控件 | 无 | 已完成 |
| macOS | ✅ | `CGWindowListCopyWindowInfo`（窗口/标题）+ AX API（焦点控件）+ `pbpaste`（剪贴板） | 需要“辅助功能/屏幕录制”授权；沙盒/公证 | 中（1 个采集器 + 签名公证） |
| Linux 桌面 | ✅（可选） | X11 `_NET_ACTIVE_WINDOW` / Wayland 受限 | Wayland 下拿不到标题，只能到应用级 | 中低 |
| Android | ✅ 本次先做 | `UsageStatsManager`（应用 + 时长，无需无障碍）+ 可选 `AccessibilityService`（窗口标题） | 需用户手动授予“使用情况访问”；国产 ROM 会杀后台 | 中 |
| 鸿蒙 HarmonyOS 4 及以下 | ✅ 直接装 Android APK | 同 Android | 同 Android | 0 额外工作 |
| 鸿蒙 HarmonyOS NEXT（5.0+） | ⚠️ 不能跑 APK | ArkTS 客户端 + `AccessibilityExtensionAbility` | 无 Android 运行时，需要单独一套代码 | 中高（另起一个工程） |

> 一句话：**Android APK 同时覆盖 Android 和鸿蒙 4.x**；鸿蒙 NEXT 要另写 ArkTS 客户端，
> 但它同样只需要输出下面这份 raw 契约，桌面/手机的时间线逻辑照样复用。

## 架构：采集器 → raw 契约 → 共享核心

```
┌─────────────┐   ┌──────────────────┐   ┌──────────────────────────────┐
│ 采集器       │──▶│ raw 事件（JSON）  │──▶│ 共享核心（纯 Python）          │
│ Win/mac/安卓 │   │ 见下方契约        │   │ 分段→规则→聚类→计费→报表→同步  │
└─────────────┘   └──────────────────┘   └──────────────────────────────┘
```

采集器**只做一件事**：按时间顺序记录“什么时候、哪个应用、什么标题”。
分段、合并、打断识别、规则归类、报表口径全部留在共享核心，避免每个平台各写一套导致口径漂移。

### raw 契约（`worktime-raw` v1）

```json
{
  "format": "worktime-raw",
  "version": 1,
  "platform": "android",
  "device": { "id": "dev-1a2b3c4d", "name": "SM-S9280" },
  "exported_at": "2026-11-13T18:00:00",
  "days": {
    "2026-11-13": {
      "activity": [
        { "ts": "2026-11-13T09:00:00", "app": "微信", "proc": "com.tencent.mm",
          "title": "", "idle_sec": 0, "screen": "active" }
      ],
      "focus": [
        { "ts": "2026-11-13T09:00:12", "app": "微信", "title": "张三",
          "text_preview": "…" }
      ]
    }
  }
}
```

- `activity` 必需，`focus` 可选；`title`/`text_preview` 允许为空（Android v0.1 就是空的）。
- 字段与本地 SQLite 的 `raw_activity` / `focus_events` 一一对应，导入即插表。
- 桌面侧命令：`wt import-raw --file raw.json`，然后照常 `wt process`。

这样 Android 端**不需要**复刻分段/规则/计费：手机负责采，桌面负责算；
两边通过同步文件夹（默认关闭、逐项勾选）或手动导出衔接。

## Android v0.1（本次实现）

**做：**
- `UsageStatsManager` 采集前台应用切换与时长（无需 root、无需无障碍）。
- 本地 SQLite，表结构与桌面一致（`raw_activity` / `focus_events` / `meta`）。
- 手机端「今天各应用用时」只读页 + 暂停/继续采集。
- 导出 `worktime-raw` JSON（分享到微信/网盘/邮件，或写入应用目录）。
- 前台服务 + 通知，被系统杀掉后可重新拉起。

**不做（v0.2 再补）：**
- 窗口标题/页面内容（需要无障碍服务，权限更重，涉及应用商店政策）。
- 手机端完整时间线编辑（先把数据接回桌面，复用现有 UI）。
- 云端/自动同步（维持本地优先，手动导出）。

## 路线图

| 阶段 | 内容 |
|---|---|
| v0.2.0（已完成） | Windows 采集 + 规则 + 同步 + 计费 |
| Android v0.1（本次） | UsageStats 采集 + 今日用量 + raw 导出 + 桌面 import-raw |
| Android v0.2 | 可选无障碍窗口标题、手机端时间线只读、直接写入共享同步文件夹 |
| macOS | 采集器（CGWindowList + AX）+ `.app` 打包与公证 |
| 鸿蒙 NEXT | ArkTS 客户端，输出同一 raw 契约 |
