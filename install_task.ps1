# 注册/更新 Windows 任务计划
# 用法：  pwsh -File install_task.ps1
#          pwsh -File install_task.ps1 -IntervalHours 4
#          pwsh -File install_task.ps1 -Remove
param(
    [int]$IntervalHours = 6,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$BASE = Split-Path -Parent $MyInvocation.MyCommand.Path
$TASK = "NetEaseRefresh"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TASK -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "已移除任务 $TASK"
    exit 0
}

# 找 pythonw.exe（无窗口解释器）
$pyw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pyw) {
    $pyw = @(
        "$env:LOCALAPPDATA\Programs\Python\Python313\pythonw.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\pythonw.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\pythonw.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $pyw -or -not (Test-Path $pyw)) {
    throw "找不到 pythonw.exe，请手动在 run_once.bat 里写死路径"
}
Set-Content -Path (Join-Path $BASE "_pythonw_path.txt") -Value $pyw -Encoding ASCII -NoNewline
Write-Host "pythonw: $pyw"

$pie = Join-Path (Split-Path $pyw) "python.exe"
& $pie -c "import Crypto, playwright" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "缺少依赖，正在安装..." -ForegroundColor Yellow
    & $pie -m pip install pycryptodome playwright
}

# 直接调 pythonw.exe：不经过 cmd，彻底没有黑窗口，也不会触发 .bat 的编码问题
# （run_once.bat 仍保留，作为手动/兼容入口）
$action = New-ScheduledTaskAction -Execute $pyw `
    -Argument "`"$BASE\run.py`"" -WorkingDirectory $BASE

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Hours $IntervalHours) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

# 注：本机策略禁用了 AtLogOn 触发器（注册时会"拒绝访问"），
# 所以只保留定时触发器。重启后的空窗靠 StartWhenAvailable 兜底：
# 任务计划会在系统恢复可用后自动补跑错过的那个时间点。

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew

# 先删再建：任务已存在时直接用 -Force 覆盖会被系统拒绝（拒绝访问），
# 这里做成幂等，重复运行安装器也安全。
Unregister-ScheduledTask -TaskName $TASK -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask -TaskName $TASK -Action $action -Trigger $trigger `
    -Settings $settings | Out-Null

$i = Get-ScheduledTaskInfo -TaskName $TASK
Write-Host ""
Write-Host "任务 $TASK 已注册：每 $IntervalHours 小时" -ForegroundColor Green
Write-Host "下次运行: $($i.NextRunTime)"
Write-Host "立即跑一次: schtasks /Run /TN $TASK"
Write-Host "日志: $BASE\logs\run.log"
Write-Host ""
Write-Host "提示：本机若启用了「电池供电时不运行」，已自动关闭该限制。"
