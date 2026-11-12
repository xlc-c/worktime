@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

set "PY=%ROOT%runtime\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" -c "import sys; print(sys.version)" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python runtime not found.
  echo Put a portable runtime in "%ROOT%runtime" or install Python 3.10+ and add it to PATH.
  pause
  exit /b 1
)

"%PY%" "scripts\init_config.py"
if errorlevel 1 (
  echo [ERROR] could not initialise config.json
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\install-autostart.ps1" -Root "%ROOT%"
if errorlevel 1 (
  echo [WARN] could not register autostart; run run-collector.bat manually each day.
)

echo.
echo ============================================================
echo  Setup complete.
echo  1. Start collecting now:   run-collector.bat
echo     (or it starts automatically at next sign-in)
echo  2. Load the extension:
echo       Chrome: chrome://extensions  -^> Developer mode -^> Load unpacked
echo       Edge:   edge://extensions    -^> Developer mode -^> Load unpacked
echo       Folder: %ROOT%extension
echo  3. Copy the token printed above into the extension options page.
echo  4. At the end of the day:  process-today.bat
echo  5. To review and correct:  review.bat
echo ============================================================
pause
