# Scan the public-release folder for personal data / secrets before publishing.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\audit-public.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Write-Host "Auditing: $root"

$exts = @("*.py", "*.js", "*.json", "*.md", "*.html", "*.ps1", "*.bat",
          "*.yml", "*.yaml", "*.css", "*.vbs", "*.txt", "*.xml", "*.example")
$files = @()
foreach ($ext in $exts) {
    $files += Get-ChildItem $root -Recurse -File -Filter $ext -ErrorAction SilentlyContinue
}
$files = $files | Where-Object {
    $_.FullName -notmatch '\\(dist|build|vendor|data|runtime|models|llama|\.git|node_modules)\\' -and
    $_.Name -ne "audit-public.ps1" -and
    $_.Extension -notin @(".png", ".jpg", ".webp", ".zip", ".db", ".wav", ".mp3")
}

$rules = @(
    @{ Name = "Windows user path"; Pattern = '[A-Za-z]:\\Users\\[^\\\s"'']+' },
    @{ Name = "Unix home path"; Pattern = '/Users/[^/\s"'']+/' },
    @{ Name = "32-hex token"; Pattern = '\b[0-9a-fA-F]{32}\b' },
    @{ Name = "Email address"; Pattern = '\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b' },
    @{ Name = "Internal marker"; Pattern = 'deepseek-harness|D:\\Backup' },
    @{ Name = "Private key"; Pattern = 'BEGIN (RSA |EC )?PRIVATE KEY' }
)

$allowedEmail = '(?i)@(example|company|invalid)\.'
$hits = @()
foreach ($file in $files) {
    $lineNo = 0
    foreach ($line in (Get-Content $file.FullName -Encoding UTF8 -ErrorAction SilentlyContinue)) {
        $lineNo++
        foreach ($rule in $rules) {
            if ($line -match $rule.Pattern) {
                if ($rule.Name -eq "Email address" -and $line -match $allowedEmail) { continue }
                $hits += [pscustomobject]@{
                    Rule = $rule.Name
                    File = $file.FullName.Substring($root.Length).TrimStart('\')
                    Line = $lineNo
                    Text = $line.Trim()
                }
            }
        }
    }
}

$placeholders = Select-String -Path (Join-Path $root "README.md"), (Join-Path $root "site\index.html") `
    -Pattern "REPLACE_ME" -ErrorAction SilentlyContinue
if ($placeholders) {
    Write-Host ""
    Write-Host "NOTE: REPLACE_ME placeholders still present (expected before publishing):"
    $placeholders | ForEach-Object { Write-Host ("  {0}:{1}" -f $_.Filename, $_.LineNumber) }
}

Write-Host ""
if ($hits.Count -gt 0) {
    $hits | Format-Table -AutoSize
    Write-Warning "$($hits.Count) suspicious match(es). Remove them before publishing."
    exit 1
}
Write-Host "OK: no suspicious patterns found in $($files.Count) files."
