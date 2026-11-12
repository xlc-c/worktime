# Contributing

Thanks for helping make WorkTime better. This project has a hard constraint:

> **Local-first, no telemetry, no cloud.** PRs that add network calls, analytics, screen
> recording, keyboard hooks or automatic uploads will be rejected.

## Development setup

- Windows 10/11 x64, Python 3.10+ (3.12 recommended).
- Optional: `pip install openpyxl uiautomation comtypes` for XLSX export and focused-text capture.
- No build step: run modules directly.

```bat
python -m unittest discover -s tests -p "test_*.py" -v
python -m wt.cli simulate --date 2026-11-06 --days 5
python -m wt.cli process --date 2026-11-06 --days 5
python -m wt.cli review
```

The review UI is static files under `wt/webui/`; backend endpoints are in `wt/review.py`.

## Areas that need help

- English localization of the UI and docs.
- Better auto-naming rules / optional local embedding clustering.
- Weekly/monthly reports and export formats.
- Portable packaging polish, signed builds, tray icon.
- Testers on Windows 10, high-DPI screens, and enterprise-restricted machines.

## Pull requests

- Keep changes focused; one topic per PR.
- Run the test suite; add tests for behavior changes (segmentation, labeling, reports).
- Do not commit personal data, `config.json`, `data/`, `dist/`, `build/`, logs or screenshots that
  contain real window titles/clipboard content. Use `wt.cli simulate` for screenshots.
- Follow the existing style (standard library preferred; no new runtime dependencies without
  discussion).

## Reporting bugs

Use the issue templates. Include: WorkTime version, Windows version, install mode (zip/dev),
what you expected, what happened, and relevant `data/logs/collector.log` lines with personal
content removed.
