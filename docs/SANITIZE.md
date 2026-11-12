# Public-release sanitization checklist

Before pushing this repository or uploading a build, confirm:

## Files that must NOT be committed

- `config.json` (contains the per-install token)
- `data/` (databases, logs, reports — captured personal content)
- `dist/`, `build/`, `vendor/`, `runtime/`, `models/`, `llama/` (binaries/models)
- `docs/review-ui*.png` and any screenshot taken from real usage
- `.venv/`, `__pycache__/`, `*.log`, `*.db*`

`.gitignore` already covers these.

## Screenshots

Only use screenshots generated from `wt.cli simulate` data. Regenerate with a clean demo DB:

```powershell
# demo DB only (never the real one)
python -m wt.cli simulate --date 2026-11-06 --days 5
python -m wt.cli process --date 2026-11-06 --days 5
python -m wt.cli review
```

Check for: real customer names, absolute paths containing a local username, email addresses, tokens.

## Automated audit

```powershell
powershell -ExecutionPolicy Bypass -File scripts\audit-public.ps1
```

It scans source/docs/site for Windows user paths, 32-hex tokens, email addresses and known
internal markers, and exits non-zero if anything is found.

## Git history

If you already committed personal data, deleting files is not enough — rewrite history
(`git filter-repo` / BFG) before publishing, or start a fresh repository from this folder.

## Build artifacts

- Publish `WorkTime.zip` + `WorkTime.zip.sha256` only.
- Never publish `config.json`, `data/`, or logs.
- Keep the release tag (`v0.1.0`) matching the version in `wt/__init__.py`.

## Third-party licenses

See `docs/components.md`. The portable ZIP bundles CPython (PSF-2.0), optional openpyxl (MIT),
uiautomation (Apache-2.0) and comtypes (MIT). Do not add GPL-incompatible dependencies without
updating the component list.
