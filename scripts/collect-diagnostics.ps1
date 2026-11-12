# Create a redacted diagnostics file for beta feedback.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\collect-diagnostics.ps1
$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root "runtime\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$stamp = Get-Date -Format "yyyyMMdd-HHmm"
$diag = Join-Path $root ("WorkTime-diagnostics-{0}.txt" -f $stamp)
$lines = @()
$lines += "WorkTime diagnostics"
$lines += "generated: " + (Get-Date -Format "s")
$os = Get-CimInstance Win32_OperatingSystem
if ($os) { $lines += ("OS: {0} {1}" -f $os.Caption, $os.Version) }
$lines += "PowerShell: " + $PSVersionTable.PSVersion.ToString()

try {
    $ver = & $py -c "import sys; sys.path.insert(0, r'$root'); import wt; print(wt.__version__)"
    $lines += "WorkTime version: $ver"
} catch {
    $lines += "WorkTime version: unknown"
}

$cfgPath = Join-Path $root "config.json"
if (Test-Path $cfgPath) {
    try {
        $cfg = Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $lines += ("ports: ingest={0} review={1}" -f $cfg.ingest_port, $cfg.review_port)
        $lines += ("token configured: {0}" -f [bool]($cfg.token))
        $lines += ("data_dir: {0}" -f $cfg.data_dir)
        $lines += ("idle_threshold_s: {0}; retention_days: {1}" -f $cfg.idle_threshold_s, $cfg.privacy.retention_days)
    } catch {
        $lines += "config.json: could not parse"
    }
}

$db = Join-Path $root "data\worktime.db"
if (Test-Path $db) {
    $counts = & $py -c @"
import sqlite3
c = sqlite3.connect(r'$db')
for t in ('raw_activity','web_events','clipboard_events','focus_events','segments','aliases'):
    try:
        print(t, c.execute('select count(*) from ' + t).fetchone()[0])
    except Exception as e:
        print(t, 'error', e)
"@
    $lines += "--- row counts (no content) ---"
    $lines += $counts
} else {
    $lines += "data/worktime.db: not found"
}

$log = Join-Path $root "data\logs\collector.log"
if (Test-Path $log) {
    $lines += "--- collector.log tail (REMOVE any window titles before sharing) ---"
    $lines += (Get-Content $log -Tail 25)
}

$lines += ""
$lines += "NOTE: this file contains NO captured content (titles/clipboard/URLs)."
$lines += "It may still contain local paths; review it before posting publicly."
$lines | Set-Content $diag -Encoding UTF8

Write-Host "Wrote: $diag"
Write-Host "Review it, remove anything personal, then attach it to your issue."
Start-Process explorer.exe -ArgumentList "/select,`"$diag`""
