@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"
set "PY=%ROOT%runtime\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" -m wt.cli collect
