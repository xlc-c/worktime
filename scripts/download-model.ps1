# Download a GGUF model for the optional local LLM labeler.
#
# Example:
#   powershell -ExecutionPolicy Bypass -File scripts\download-model.ps1 `
#     -Url "https://huggingface.co/<repo>/resolve/main/<file>.gguf" -FileName "model.gguf"
#
# Recommended: a Qwen3-4B Q4_K_M GGUF (~2.5 GB) for 4-core / 16 GB machines.
# Search Hugging Face for "Qwen3-4B-GGUF" and copy the *resolve/main/*.gguf link.
# Target machines are offline: download here, then copy models\model.gguf over.

param(
    [Parameter(Mandatory = $true)][string]$Url,
    [string]$FileName = "model.gguf"
)

$root = Split-Path -Parent $PSScriptRoot
$models = Join-Path $root "models"
New-Item -ItemType Directory -Force $models | Out-Null
$dest = Join-Path $models $FileName

Write-Host "Downloading to $dest ..."
try {
    Invoke-WebRequest -Uri $Url -OutFile $dest -UseBasicParsing
} catch {
    Write-Error "Download failed: $_"
    exit 1
}

$size = [math]::Round((Get-Item $dest).Length / 1GB, 2)
Write-Host "Done: $dest ($size GB)"
Write-Host "Next:"
Write-Host "  1. set llm.enabled = true in config.json"
Write-Host "  2. put llama-server.exe into the llama\ folder"
Write-Host "  3. run run-llm.bat (leave it running) before process-today.bat"
