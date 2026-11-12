@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"
set "PY=%ROOT%runtime\python.exe"
if not exist "%PY%" set "PY=python"
echo 复核页地址: http://127.0.0.1:18732/  （浏览器会自动打开；没弹出就手动访问）
"%PY%" -m wt.cli review
