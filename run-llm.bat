@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

if not exist "%ROOT%llama\llama-server.exe" (
  echo [ERROR] llama-server.exe not found.
  echo Put the llama.cpp Windows build in "%ROOT%llama" first.
  echo Download: https://github.com/ggml-org/llama.cpp/releases  ^(choose win-x64, CPU^)
  pause
  exit /b 1
)
if not exist "%ROOT%models\model.gguf" (
  echo [ERROR] models\model.gguf not found.
  echo See scripts\download-model.ps1 for how to fetch a GGUF model.
  pause
  exit /b 1
)

echo Starting local LLM on http://127.0.0.1:8080 (CPU only)...
"%ROOT%llama\llama-server.exe" -m "%ROOT%models\model.gguf" --host 127.0.0.1 --port 8080 -t 4 -c 4096 --parallel 1
