# Changelog

## v0.2.1 — 2026-11-13

Cross-platform groundwork: the capture layer is now per-OS and everything else
stays shared.

### Added

- **`worktime-raw` v1 contract** (`wt/importers.py`, `docs/PLATFORMS.md`): any
  platform's collector can export raw activity and the desktop runs the same
  segmentation/rules/reports. CLI: `wt import-raw --file raw.json`
  (`--keep` appends instead of replacing a day).
- **Android app v0.1** (`android/`, Java, framework APIs only): UsageStats capture
  (no root, no accessibility), foreground service, today's per-app usage,
  pause/resume, `worktime-raw` export via share sheet or clipboard.
- **CI**: `.github/workflows/android.yml` builds the debug APK on every push
  under `android/`, attaches it to the `android-v0.1.0` prerelease, and posts the
  Gradle log to a public issue when the build fails.

### Fixed

- `Store.delete_raw_day()` / `count_raw_day()` for safe re-imports of the same day.

## v0.2.0 — 2026-11-13

Focus: make the timeline trustworthy without a babysitter — rules instead of
hand-dragging, sync you control channel by channel, billing, and a visible
collector.

### Added

- **Automatic rules** (`wt/rules.py`, `wt rules …`): deterministic
  “app/title/domain/focused-text → matter” mapping with `contains` / `=exact` /
  `re:` regex, priorities, hit counters and a dry-run test command. Rules run
  before clustering; manual labels and learned aliases still win. UI: 设置 → 自动规则,
  plus 「存为规则」 in the segment drawer.
- **Opt-in multi-device sync** (`wt/sync.py`, `wt/crypto.py`, `wt sync …`):
  bundle export/import through a folder you choose (OneDrive, NAS, USB), with
  **per-channel manual switches** (times / matters / window titles / URLs /
  page text / focused text / clipboard). Imported days live in `foreign_days`,
  never mixed into local segments, and are idempotent per device+day. Optional
  passphrase encryption (ChaCha20 + HMAC-SHA256, scrypt or PBKDF2 KDF).
- **Billing** (`wt/billing.py`, `wt matter …`, `wt invoice`): per-matter hourly
  rates with parent inheritance (`Client / Project / Sub-task`), billable flag,
  configurable rounding, Markdown + CSV invoices, and amount columns in period
  reports.
- **Live collector status**: heartbeat in the DB, `/api/live`, a status pill and
  a pause/resume button in the review UI, auto-refresh of today's timeline, and
  `scripts/worktime-tray.ps1` (Windows tray icon with the same controls).
- **`enterprise` capture preset**: window titles + idle only — no extension, no
  focused text, no clipboard — for DLP-restricted machines.
- Report weekly/monthly/yearly views can include other devices' imported days
  when sync is enabled.

### Changed

- Clipboard previews for high-entropy content (card numbers, tokens, long random
  strings) are dropped and only hash + length are stored; secrets are still
  skipped entirely.
- Focused-text capture now skips password controls (`IsPassword`) and excluded
  apps, and truncates to `uia_max_chars` (default 300).
- Reports carry a `device` column and billable totals when rates exist.
- `requirements.txt` added (uiautomation / comtypes / openpyxl).

### Fixed

- README test badge and roadmap listed already-shipped features as planned and
  undercounted tests (now 64).
- Release notes referenced `WorkTime.zip` while the asset is
  `WorkTime-v0.1.0.zip`.
- `wt/__init__.py` version now matches the release.

## v0.1.0 — 2026-11-12

First public prototype.

- Automatic capture: foreground window, idle/away, clipboard (hash + preview), focused UI text
  (via UI Automation), browser page context via Chrome/Edge MV3 extension.
- Deterministic segmentation: merge/absorb/URL-split, clipboard “task glue”, breaks.
- Labeling: pure-Python TF-IDF clustering + deterministic naming + alias learning; optional local
  OpenAI-compatible LLM (llama.cpp / Qwen GGUF) for cluster naming.
- Visual review UI: per-app timeline, 24h overview bar, charts, drag to move/resize, drag to a
  matter to tag, multi-select bulk labels, undo, split/merge, interruption detection (⚡),
  vertical in-segment split timeline with draggable handle, embedded web/focus/clipboard content,
  hierarchical matters (`Parent / Child`), cross-highlighting between overview/timeline/table/charts.
- Reports: Markdown, CSV, XLSX (raw content excluded).
- Portable packaging: bundled Python runtime, per-user Startup shortcut, uninstall script,
  SHA-256 published with each release; no admin rights required.
- Docs: privacy notice, component/license list, Chinese IT-approval template, test data generator.
