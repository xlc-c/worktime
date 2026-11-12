@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v WorkTimeCollector /f >nul 2>&1
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\WorkTime Collector.lnk" >nul 2>&1
echo Removed autostart entries (Startup shortcut + legacy Run key).

powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*wt.cli collect*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
echo Stopped collector process (if it was running).

if /i "%~1"=="/D" (
  echo Deleting captured data in "%ROOT%data" ...
  rd /s /q "%ROOT%data"
  echo Data deleted.
) else (
  echo Captured data kept in "%ROOT%data". Run: uninstall-user.bat /D  to delete it.
)

echo.
echo Remove the extension manually in Chrome/Edge (chrome://extensions / edge://extensions).
echo Then delete this folder.
pause
