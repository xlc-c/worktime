# Build a portable folder that can be copied to a machine WITHOUT admin rights.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\package-portable.ps1 `
#     -PythonDir "C:\Path\To\Python312" -OutDir "dist\WorkTime" -Zip
#
# PythonDir must be a full CPython installation (python.exe + DLLs + Lib).
# You can use the embeddable "python-3.12.x-embed-amd64" extracted over a full
# install, or any normal Python 3.10+ directory.

param(
    [Parameter(Mandatory = $true)][string]$PythonDir,
    [string]$OutDir = "dist\WorkTime",
    [switch]$Zip
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $root $OutDir
$py = Join-Path $PythonDir "python.exe"

if (-not (Test-Path $py)) {
    Write-Error "python.exe not found under $PythonDir"
    exit 1
}

if (Test-Path $out) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Force $out | Out-Null
New-Item -ItemType Directory -Force (Join-Path $out "runtime") | Out-Null

Write-Host "Copying Python runtime (minimal)..."
$runtime = Join-Path $out "runtime"
Copy-Item (Join-Path $PythonDir "python.exe") $runtime
Copy-Item (Join-Path $PythonDir "pythonw.exe") $runtime -ErrorAction SilentlyContinue
Get-ChildItem -Path $PythonDir -Filter "*.dll" | Copy-Item -Destination $runtime
Copy-Item (Join-Path $PythonDir "DLLs") $runtime -Recurse
Copy-Item (Join-Path $PythonDir "Lib") $runtime -Recurse

# site-packages: only the optional pure-python packages we might use.
$site = Join-Path $runtime "Lib\site-packages"
if (Test-Path $site) {
    Get-ChildItem $site -Directory | Where-Object {
        $_.Name -notin @("openpyxl", "et_xmlfile", "uiautomation", "comtypes")
    } | Remove-Item -Recurse -Force
    Get-ChildItem $site -File | Remove-Item -Force
}

# Optional UIA packages vendored under vendor\site-packages (uiautomation/comtypes).
$vendor = Join-Path $root "vendor\site-packages"
if ((Test-Path $vendor) -and (Test-Path $site)) {
    Write-Host "Copying vendored optional packages (uiautomation/comtypes)..."
    Copy-Item (Join-Path $vendor "*") $site -Recurse -Force
}

Write-Host "Copying application files..."
Copy-Item (Join-Path $root "wt") $out -Recurse
Copy-Item (Join-Path $root "scripts") $out -Recurse
Copy-Item (Join-Path $root "extension") $out -Recurse
Copy-Item (Join-Path $root "config.example.json") $out
Get-ChildItem $root -Filter "*.bat" | Copy-Item -Destination $out
Get-ChildItem $root -Filter "*.vbs" | Copy-Item -Destination $out
if (Test-Path (Join-Path $root "README.md")) {
    Copy-Item (Join-Path $root "README.md") $out
}
# docs/ is delivered separately for the IT/compliance review, not on the target PC.

# Drop caches copied along the way.
Get-ChildItem $out -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem $out -Recurse -Filter "*.pyc" | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "Portable folder ready: $out"
if ($Zip) {
    $zipPath = "$out.zip"
    if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
    Compress-Archive -Path (Join-Path $out "*") -DestinationPath $zipPath
    Write-Host "Zip: $zipPath"
}
Write-Host "Next: copy the folder to the target machine and run setup-user.bat."
