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
    [switch]$Zip,
    [switch]$KeepTestTools
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $root $OutDir
$py = Join-Path $PythonDir "python.exe"

if (-not (Test-Path $py)) {
    Write-Error "python.exe not found under $PythonDir"
    exit 1
}

# Version comes from wt\__init__.py so the asset name always matches the code.
$version = "0.0.0"
$initFile = Join-Path $root "wt\__init__.py"
if (Test-Path $initFile) {
    $m = Select-String -Path $initFile -Pattern '__version__\s*=\s*"([^"]+)"'
    if ($m) { $version = $m.Matches[0].Groups[1].Value }
}
Write-Host "Packaging WorkTime v$version"

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

# Drop stdlib pieces a background collector never imports (keeps the ZIP small).
$lean = @("test", "tests", "idlelib", "tkinter", "turtledemo", "lib2to3",
          "ensurepip", "pydoc_data", "unittest\test")
if (-not $KeepTestTools) {
    foreach ($dir in $lean) {
        $path = Join-Path $runtime "Lib\$dir"
        if (Test-Path $path) { Remove-Item -Recurse -Force $path -ErrorAction SilentlyContinue }
    }
    $tcl = Join-Path $runtime "tcl"
    if (Test-Path $tcl) { Remove-Item -Recurse -Force $tcl -ErrorAction SilentlyContinue }
}

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
Copy-Item (Join-Path $root "requirements.txt") $out
Copy-Item (Join-Path $root "LICENSE") $out
Copy-Item (Join-Path $root "CHANGELOG.md") $out
Get-ChildItem $root -Filter "*.bat" | Copy-Item -Destination $out
Get-ChildItem $root -Filter "*.vbs" | Copy-Item -Destination $out
foreach ($doc in @("README.md", "README.zh-CN.md")) {
    if (Test-Path (Join-Path $root $doc)) { Copy-Item (Join-Path $root $doc) $out }
}
# docs/ is what IT/compliance reviewers read; ship it with the ZIP.
if (Test-Path (Join-Path $root "docs")) {
    New-Item -ItemType Directory -Force (Join-Path $out "docs") | Out-Null
    foreach ($doc in @("privacy.md", "IT-审批材料.md", "RULES.md", "SYNC.md",
                       "BILLING.md", "components.md")) {
        $src = Join-Path $root "docs\$doc"
        if (Test-Path $src) { Copy-Item $src (Join-Path $out "docs") }
    }
}

# Drop caches copied along the way.
Get-ChildItem $out -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem $out -Recurse -Filter "*.pyc" | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem $out -Recurse -Filter "*.pyo" | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "Portable folder ready: $out"
if ($Zip) {
    $zipPath = Join-Path (Split-Path -Parent $out) "WorkTime-v$version.zip"
    if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::Open($zipPath, "Create")
    try {
        $base = (Resolve-Path $out).Path.TrimEnd('\')
        Get-ChildItem $out -Recurse -File | ForEach-Object {
            # Forward slashes only: some extractors (and the portable runtime's
            # own zip handling) treat backslash entries as literal file names.
            $relative = $_.FullName.Substring($base.Length + 1).Replace('\', '/')
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $zip, $_.FullName, $relative, [System.IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
        }
    } finally {
        $zip.Dispose()
    }
    $hash = (Get-FileHash $zipPath -Algorithm SHA256).Hash
    Write-Host "Zip:  $zipPath"
    Write-Host "SHA256: $hash"
}
Write-Host "Next: copy the folder to the target machine and run setup-user.bat."
