@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"
set "PY=%ROOT%runtime\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" -m wt.cli live
echo.
echo 提示：托盘里可以暂停/恢复采集；复核页右上角也有同样按钮。
pause
