# Beta testing guide

## For testers

1. Download `WorkTime.zip` from Releases, verify SHA-256, extract to `%LOCALAPPDATA%\WorkTime\`.
2. Run `setup-user.bat`; load the extension in Chrome/Edge; paste the token.
3. Work normally for 1–2 days with the collector running.
4. Each evening: `process-today.bat`, open `review.bat`, spend 3–5 minutes correcting labels.
5. After 3 days, send feedback via GitHub Discussions / Issues.

Please **do not attach real window titles, clipboard text, customer names or screenshots of
company data** to public issues. Use the redacted diagnostics bundle:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\collect-diagnostics.ps1
```

It contains version, OS, row counts (no content), redacted config and the last log lines.

## Feedback questions

1. Install path & Windows version; did `setup-user.bat` work without admin?
2. Which apps did it capture well / poorly? (Excel, Outlook, Lync/Teams, browsers, ERP, RDP…)
3. Roughly what % of auto-generated task/matter labels were correct out of the box?
4. How many minutes per day did review take? Which steps felt slow?
5. Did interruption (⚡) detection match reality? False positives?
6. Content drawer: useful? anything it should show or hide?
7. Privacy: anything captured that surprised you? Which preset/scope did you use, and did your
   company require locking anything off?
8. Would you keep using it? What single change matters most?

## For maintainers

- Label issues: `beta`, `capture`, `ui`, `labeling`, `reports`, `packaging`, `privacy`.
- Triage weekly; reply to every beta report within 48h.
- Cut a patch release every week during beta; keep `CHANGELOG.md` current.
- Track acceptance rate by asking testers to count “segments I had to edit” vs total segments.
- Never ask testers to upload their database; ask for counts + redacted logs only.
