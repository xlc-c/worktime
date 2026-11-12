# WorkTime · 本机工作时间线（中文说明）

> 一个 Windows 上**完全本地**的工作时间统计工具：自动记录前台窗口、浏览器页面、
> 焦点输入框和复制粘贴，把一天切成时间线；可以拖动、打标签、拆分、查看内容；
> 支持日报 / 周报 / 月报 / 年报，以及四档采集权限预设。
> **无云端、无遥测、无截图、无键盘钩子**，免管理员权限即可运行。

![时间线](docs/screenshots/full.png)

## 功能

- **自动时间线**：应用、窗口标题、浏览器 URL/标题/可见文字、Excel 单元格与邮件正文焦点文本、
  复制粘贴、空闲/离开；浏览器部分由 Chrome/Edge 扩展补充。
- **可视化复核**：按应用分层的时间线、24 小时概览、事项环形图、应用用时、每小时活跃；
  色块可拖动移动、拉边缘改时长、拖到「事项」上打标签；支持多选批量、撤销、拆分/合并。
- **打断识别**：短时间插入在两段同一程序之间（邮件 → Lync 消息 → 回邮件）会标 ⚡。
- **内容抽屉**：网页正文、焦点输入、复制粘贴按需显示；默认打码，导出不含原文。
- **层级事项**：`客户 / 项目 / 子任务`，色块按父级配色，图表按父级汇总。
- **报告**：日报 / 周报 / 月报 / 年报，含 KPI、环形图、应用条形图、按天/按月活跃图，
  可下载 Markdown。
- **权限预设**：严格 / 仅元数据 / 标准 / 完整；窗口标题、URL、网页正文、焦点输入、
  剪贴板、空闲逐项开关；可排除程序与域名、设置保留期；IT 可用 `policy.locked` 锁定。
- **可选本地 LLM**：llama.cpp + Qwen GGUF（CPU 即可）给聚类结果命名；不装也能用。

![详情抽屉](docs/screenshots/drawer.png)

## 隐私设计

| 原则 | 实现 |
|---|---|
| 只在本机 | SQLite 存在程序目录，HTTP 只绑定 `127.0.0.1` |
| 无遥测/自动更新 | 不访问外网，不收集使用数据 |
| 无截图/无键盘钩子 | 只读焦点控件文本，不记录原始按键 |
| 剪贴板最小化 | 只存哈希 + 前 N 字符；密码管理器黑名单 |
| 可删除 | 保留期可配，卸载脚本一键删除 |

本工具定位是**个人效率工具**，不是员工监控软件；公司使用请走 IT 审批与知情同意。

## 快速开始

1. 从 Releases 下载 `WorkTime.zip`，解压到 `%LOCALAPPDATA%\WorkTime\`；
2. 运行 `setup-user.bat`（生成 token、创建启动快捷方式）；
3. Chrome/Edge 加载 `extension` 目录，并填入 token；
4. `run-collector.bat` 开始采集；下班 `process-today.bat`，`review.bat` 打开界面。

> 未签名，SmartScreen 会提示；请核对 Release 里的 SHA-256，或从源码构建。

## 从源码运行

```bat
python -m unittest discover -s tests -p "test_*.py" -v
python -m wt.cli simulate --date 2026-11-06 --days 5
python -m wt.cli process --date 2026-11-06 --days 5
python -m wt.cli review
```

## 参与

- 反馈/内测：GitHub Discussions（Q&A / Ideas / Show your setup）；
- 想发群/社区：`docs/SHARE.md` 有可直接复制的文案；
- 请保持 **local-first / 无遥测** 的约束；安全报告见 `SECURITY.md`。

## 许可

MIT，见 [LICENSE](LICENSE)。
