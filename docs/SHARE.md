# 发到群里 / 社区用的求助与推广文案

> 直接复制下面任一段，把 `{{REPO}}` / `{{SITE}}` / `{{ZIP}}` 换成你的链接。
> **不要**发真实工作数据、客户名、公司截图；演示图都用 `wt.cli simulate` 的模拟数据。

## A. 短版（AI 群 / 微信群 / QQ 群 / Telegram / Discord）

> 大家好，我做了一个**完全本地**的 Windows 工作时间线工具（开源 MIT），想请大家帮忙试试、出出主意。
>
> 它自动记录前台窗口、浏览器页面、焦点输入框和复制粘贴，把一天切成时间线，可以拖动、打标签、拆分；能识别“处理邮件时被 Lync 消息打断”这类场景；数据只在本机，没有云、没有遥测、无截图、无键盘钩子，免管理员权限。
>
> 试用：{{ZIP}}（下载后看 README）；源码/反馈：{{REPO}}
>
> 特别想听：① 自动命名准不准 ② 每天复核要几分钟 ③ 哪些场景识别不了（Excel 多 sheet、Outlook 预览窗格、Teams、远程桌面…）④ 公司权限允许记录哪些内容。
> 群里可以直接回我，或者去 GitHub Discussions 留个反馈。谢谢！

## B. 中版（V2EX 分享创造 / 即刻 / 少数派 / 知乎想法）

> **分享创造：一个完全本地的 Windows 工作时间线工具**
>
> 起因很简单：同时开浏览器、邮箱、Lync、Excel 来回跳，一天下来却说不清时间花在哪。
>
> WorkTime 会记录前台窗口、浏览器 URL/可见文字、Excel/邮件焦点文本、复制粘贴和空闲状态，切成一条可回放的时间线；支持拖动调时间、拖到事项上打标签、Shift 多选批量、拆分/合并、撤销；它会自动识别“短时间插入在两段同程序之间”的打断；事项支持“客户/项目/子任务”层级。
>
> 隐私是设计的一部分：SQLite 本机存储、HTTP 只绑 127.0.0.1、无遥测、无截图、无键盘钩子，剪贴板只存前 240 字+哈希；还做了 strict/metadata/standard/full 四档采集预设和 IT 锁定开关，方便不同公司按权限收紧。
>
> 开源 MIT，Windows 10/11，便携包免管理员：{{ZIP}} ｜ 源码与反馈：{{REPO}} ｜ 介绍页：{{SITE}}
>
> 想找 20–30 个内测用户，重点验证自动命名准确率、复核耗时、识别不了的应用/网页场景。欢迎在群里或 GitHub 直接提。

## C. English (Reddit / Discord / Show HN)

> **Show WorkTime – local-first work timeline for Windows (open source, no cloud, no telemetry)**
>
> I kept switching between browser, mail, Lync and Excel all day and couldn't answer “what did I actually do?”. So I built WorkTime: it records the foreground window, browser page, focused UI text and copy/paste events, segments the day into a timeline, and lets you drag blocks into projects/tasks.
>
> It flags interruptions (a 2-minute Lync message between two email-reading segments), handles clipboard “task glue” (copy in browser → paste in Excel), supports hierarchical matters (client / project / subtask), and has four capture presets (strict / metadata / standard / full) with an IT-lockable policy — useful for companies that allow different levels of data.
>
> Privacy: SQLite on-device, HTTP on 127.0.0.1 only, no telemetry, no screenshots, no keyboard hooks, clipboard stored as hash + 240 chars. MIT, Windows 10/11, portable ZIP, no admin rights.
>
> Code: {{REPO}} · Site: {{SITE}} · Release: {{ZIP}}
>
> I'm looking for beta testers — especially: how accurate is auto-labeling, how long does daily review take, which apps/pages fail (Excel multi-sheet, Outlook preview pane, Teams, RDP), and what capture scope your company would allow.

## D. 希望群友帮忙验证的具体问题

复制到群里时可以附上这几条：

1. 你的环境（Windows 10/11、公司电脑/个人电脑、有无管理员权限）；
2. 自动生成的任务/事项，大概多少比例是准确的？
3. 每天复核花几分钟？哪一步最烦？
4. 哪些场景完全识别不了（例如同一个 Excel 文件多个 sheet、网页 SPA、远程桌面、Citrix）？
5. 公司允许记录到哪一档：应用名/标题/URL/正文/焦点文本/剪贴板？
6. 有没有误采集敏感内容（银行、密码管理器、客户信息）？
7. 安装/扩展/杀软有没有被拦？

## E. 发帖注意

- 截图用 `docs/screenshots/` 里的模拟数据图，或自己用 `wt.cli simulate` 生成；
- 群文件发 **ZIP + SHA256**，不要发 `config.json` / `data/`；
- GitHub 上先开 Discussions（Q&A / Ideas / Show your setup），把群里的反馈沉淀成 issue；
- 说明这是 v0.1 原型、未签名，SmartScreen 会提示；介意的话可从源码构建。
