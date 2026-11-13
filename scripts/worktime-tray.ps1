# WorkTime tray icon: shows whether capture is running, and pauses/resumes it.
#
# Usage:  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\worktime-tray.ps1
# It talks to the local review server (127.0.0.1) only; no network, no admin.
param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [int]$Port = 18732
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$script:baseUrl = "http://127.0.0.1:$Port"
$script:paused = $false
$script:alive = $false

function Get-LiveState {
    try {
        $state = Invoke-RestMethod -Uri "$script:baseUrl/api/live" -TimeoutSec 3
        return $state
    } catch {
        return $null
    }
}

function Set-CapturePaused {
    param([bool]$Paused)
    try {
        $body = @{ paused = $Paused } | ConvertTo-Json
        Invoke-RestMethod -Uri "$script:baseUrl/api/collector/pause" -Method Post `
            -ContentType "application/json" -Body $body -TimeoutSec 3 | Out-Null
        return $true
    } catch {
        return $false
    }
}

$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Application
$notify.Text = "WorkTime"
$notify.Visible = $true

$menu = New-Object System.Windows.Forms.ContextMenuStrip
$openItem = $menu.Items.Add("打开时间线")
$pauseItem = $menu.Items.Add("暂停采集")
$folderItem = $menu.Items.Add("打开同步文件夹")
$quitItem = $menu.Items.Add("退出托盘")

$openItem.Add_Click({ Start-Process "$script:baseUrl/" })
$folderItem.Add_Click({
    $cfg = Join-Path $Root "config.json"
    $folder = ""
    if (Test-Path $cfg) {
        try {
            $json = Get-Content $cfg -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($json.sync -and $json.sync.folder) { $folder = $json.sync.folder }
        } catch { }
    }
    if ($folder -and (Test-Path $folder)) {
        Start-Process explorer.exe $folder
    } else {
        Start-Process explorer.exe $Root
    }
})
$pauseItem.Add_Click({
    $target = -not $script:paused
    if (Set-CapturePaused $target) {
        $script:paused = $target
        $notify.BalloonTipTitle = "WorkTime"
        if ($target) {
            $notify.BalloonTipText = "已暂停采集；时间线不会写入新数据。"
        } else {
            $notify.BalloonTipText = "已恢复采集。"
        }
        $notify.ShowBalloonTip(2000)
    } else {
        $notify.BalloonTipTitle = "WorkTime"
        $notify.BalloonTipText = "复核页没在运行，先双击 review.bat。"
        $notify.ShowBalloonTip(3000)
    }
})
$quitItem.Add_Click({
    $notify.Visible = $false
    $notify.Dispose()
    [System.Windows.Forms.Application]::Exit()
})
$notify.ContextMenuStrip = $menu
$notify.Add_MouseDoubleClick({ Start-Process "$script:baseUrl/" })

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 5000
$timer.Add_Tick({
    $state = Get-LiveState
    if ($null -eq $state) {
        $script:alive = $false
        $notify.Text = "WorkTime · 复核页未运行"
        $pauseItem.Text = "暂停采集"
        return
    }
    $script:paused = [bool]$state.paused
    $script:alive = [bool]$state.alive
    if ($script:paused) {
        $notify.Text = "WorkTime · 已暂停"
        $pauseItem.Text = "恢复采集"
    } elseif ($script:alive) {
        $age = 0
        if ($null -ne $state.age_s) { $age = [int]$state.age_s }
        $notify.Text = "WorkTime · 采集中（$age 秒前）"
        $pauseItem.Text = "暂停采集"
    } else {
        $notify.Text = "WorkTime · 采集器未运行"
        $pauseItem.Text = "暂停采集"
    }
})
$timer.Start()

[System.Windows.Forms.Application]::Run()
