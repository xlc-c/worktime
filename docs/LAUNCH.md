# Publishing & promotion playbook

This folder is already sanitized for public release. Before pushing, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\audit-public.ps1
```

Fix every hit. Then follow the steps below.

## 0. One-time decisions

- Repository name: `worktime` (or `WorkTime`).
- License: MIT (already in `LICENSE`).
- Version: `v0.1.0` (prototype / beta).
- Languages: English README + Chinese section; UI is Chinese-first for now.
- Downloads: GitHub Releases only (portable ZIP + SHA-256). No installers.

## 1. Replace placeholders

Search for `xlc-c`:

- `README.md`, `site/index.html`, `.github/ISSUE_TEMPLATE/config.yml`
- Replace `xlc-c/worktime` with `<your-github-user>/worktime`
- If you use a custom domain, update `site/index.html` links.

## 2. Create the repository

```bash
cd publish/worktime
git init
git add .
git commit -m "WorkTime v0.1.0: local-first work timeline for Windows"
git branch -M main
gh repo create <your-user>/worktime --public --source=. --push
# or: git remote add origin https://github.com/<your-user>/worktime.git && git push -u origin main
```

Check the rendered README on GitHub and the issue templates.

## 3. Cut the first release (builds the ZIP in CI)

```bash
git tag v0.1.0
git push origin v0.1.0
```

The `release` workflow runs tests, builds `WorkTime.zip` with a bundled Python runtime, writes
`WorkTime.zip.sha256`, and publishes a GitHub Release. Verify:

- Release contains both files.
- SHA-256 matches the local build if you also build locally.
- Download + extract + `setup-user.bat` works on a clean Windows VM.

> Unsigned ZIP → SmartScreen warning is expected. Put the SHA-256 and “build from source” note
> in the release notes (the workflow already attaches the checksum).

## 4. Landing page (GitHub Pages)

1. Push the repo (the `pages` workflow deploys `site/`).
2. GitHub → Settings → Pages → Source: **GitHub Actions**.
3. Wait for the `pages` workflow; the URL is shown in Actions/Pages.
4. Add the URL to the repo description and release notes.

The site is a single static page with local assets — no CDN, no tracking.

## 5. Beta program (the actual point)

Goal: 20–30 testers across Windows 10/11, office laptops, high-DPI, enterprise-restricted machines.

Collect via GitHub Discussions (or a simple form) with these questions:

1. Install path (ZIP/portable/source) and Windows version.
2. Did capture work for Excel/Outlook/Lync/Teams? What was missing?
3. After a full day, how accurate were the auto-generated tasks/matters (rough %)?
4. How long did daily review take?
5. What did you expect the timeline to show that it didn’t?
6. Privacy: anything captured that shouldn’t be?
7. Would you keep using it? Why / why not?

Ask testers to run `scripts\collect-diagnostics.ps1` and attach the ZIP (no captured content).

Cadence: one release per week during beta; label issues `beta`, `capture`, `ui`, `labeling`,
`packaging`; publish a short “what changed this week” Discussion.

## 6. Promotion channels

Order matters: start where “local-first / self-hosted / privacy” audiences already are.
Copy-paste drafts for group chats (AI 群 / 微信群 / Discord / Telegram) are in
[`SHARE.md`](SHARE.md).

### Hacker News — Show HN

> **Show HN: WorkTime – local-first work timeline for Windows (no cloud, no telemetry)**
>
> I wanted to answer “what did I actually do today?” without a cloud tracker or screenshots.
> WorkTime records the foreground window, browser page, focused UI text and copy/paste events,
> segments the day into a timeline, and lets you drag blocks into projects/tasks. Everything is
> local (SQLite + 127.0.0.1), the browser extension only talks to localhost, and there’s no
> telemetry. UI is a local web page served by the app.
>
> It handles interruptions (short Lync message between two email segments), clipboard “task glue”
> (copy from browser → paste into Excel), hierarchical matters (client / project / subtask), and an
> optional CPU-only local LLM for naming clusters. Windows 10/11, portable ZIP, no admin rights.
>
> Open source MIT: <link>. Feedback very welcome, especially on auto-labeling accuracy and what a
> good daily review flow looks like.

### Reddit (respect each subreddit’s self-promotion rules)

- r/selfhosted — angle: local-only, SQLite, no cloud; ask for feedback.
- r/Windows11 — angle: portable, no admin, privacy; include screenshots.
- r/productivity — angle: time audit + review flow, not promotion.
- r/opensource — angle: architecture, clustering, extension.
Avoid cross-posting the same text in one day; reply to every comment.

### V2EX（分享创造）/ 少数派 / 知乎 / 即刻

V2EX 标题建议：**分享创造 · 做了一个完全本地的 Windows 工作时间线工具（开源）**

> 起因是想知道一天到底在哪些事情上来回跳。它记录前台窗口、浏览器页面、焦点输入框和复制粘贴，
> 切成时间线后可以拖动、打标签、拆分，能识别“邮件处理中被 Lync 打断”。
> 数据只在本机 SQLite，浏览器扩展只发 127.0.0.1，无截图无键盘钩子，免管理员权限。
> 想找一批人试用，重点想听：自动命名准不准、每天复核要几分钟、哪些场景识别不了。

少数派/知乎：写“为什么做 / 怎么实现 / 隐私设计 / 使用一周后的数据”这类长文，而不是硬广；
附演示 GIF/视频更有效。

### Product Hunt（等 v0.2 有英文 UI 后再发）

Tagline: “Your day, reconstructed — local-first work timeline for Windows.”
First comment: privacy architecture + ask for feedback.

### Short video / X

30–60s: morning capture → drag a block → tag → interruption flag → daily report. Caption:
“No cloud. No screenshots. Windows. Open source.”

## 7. Metrics that matter (no telemetry — ask, don’t track)

- Downloads → successful setup (ask in Discussion poll).
- 7-day retention (self-reported / returning testers).
- Auto-label acceptance rate: share of segments not edited after a day.
- Review time per day (target < 5 min).
- Top missing capture scenarios (Excel sheets, Outlook preview, Teams, Citrix/RDP…).
- Privacy concerns raised (fix docs/UX accordingly).

## 8. Known launch risks

| Risk | Mitigation |
|---|---|
| “Clipboard tracking” sounds scary | README + landing privacy section; hash + 240 chars; no screenshots; password managers excluded |
| SmartScreen / AV warnings | Publish SHA-256; build from source; later sign via SignPath/Azure Trusted Signing |
| Enterprise extension policy blocks unpacked extension | Document fallback (window title + clipboard only); offer IT allowlist guidance |
| Chinese-only UI limits global reach | Ship English UI in v0.2; landing page already bilingual |
| Feature requests for cloud sync | Keep local-first; offer LAN-only export/merge instead |

## 9. Launch week schedule

- Day 1: publish repo + release + Pages; post Show HN (morning US time).
- Day 2: V2EX + 少数派 draft; answer comments.
- Day 3: Reddit (one subreddit), short video.
- Day 4–5: fix top 3 feedback items; cut `v0.1.1`.
- Week 2: publish “what we learned from 20 testers” post; start English UI work.
