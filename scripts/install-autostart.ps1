# Register WorkTime to start with Windows for the current user.
#
# Creates a shortcut in the user's Startup folder that runs run-collector.bat
# minimized. No administrator rights required. English-only text on purpose:
# Windows PowerShell 5.1 may misread UTF-8 without BOM on Chinese systems.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\install-autostart.ps1 [-Root <app folder>]

param([string]$Root = "")

$ErrorActionPreference = "Stop"
if (-not $Root) { $Root = Split-Path -Parent $PSScriptRoot }
$Root = (Resolve-Path $Root).Path

$bat = Join-Path $Root "run-collector.bat"
if (-not (Test-Path $bat)) {
    Write-Error "run-collector.bat not found under $Root"
    exit 1
}

$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "WorkTime Collector.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $bat
$shortcut.WorkingDirectory = $Root
$shortcut.WindowStyle = 7   # minimized
$shortcut.Description = "WorkTime background collector (minimized; close it to stop)"
$shortcut.Save()

# Convenience desktop shortcut that opens the local review UI.
$reviewBat = Join-Path $Root "review.bat"
if (Test-Path $reviewBat) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $uiShortcut = $shell.CreateShortcut((Join-Path $desktop "WorkTime UI.lnk"))
    $uiShortcut.TargetPath = $reviewBat
    $uiShortcut.WorkingDirectory = $Root
    $uiShortcut.WindowStyle = 1
    $uiShortcut.Description = "Open WorkTime review UI (http://127.0.0.1:18732/)"
    $uiShortcut.Save()
    Write-Host "Desktop shortcut created:"
    Write-Host "  $(Join-Path $desktop 'WorkTime UI.lnk')"
}

# Remove the legacy HKCU Run entry if an older build created one.
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
if (Test-Path $runKey) {
    Remove-ItemProperty -Path $runKey -Name "WorkTimeCollector" -ErrorAction SilentlyContinue
}

Write-Host "Startup shortcut created:"
Write-Host "  $shortcutPath"
Write-Host "  -> $bat (minimized)"
