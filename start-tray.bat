@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\worktime-tray.ps1" -Root "%ROOT%"
