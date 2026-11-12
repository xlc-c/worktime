# Changelog

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
