#requires -RunAsAdministrator
<#
    서버 PC에서 한 번만 실행한다. 검색 색인을 주기적으로 최신으로 유지한다.

    웹 서버(ThinkwiseWiki)와 별도의 작업으로 등록하는 이유:
    동기화가 실패해도 웹 서버는 그대로 떠서 검색이 계속 되어야 하기 때문이다.
    한 프로세스에 묶으면 한쪽 사고가 다른 쪽을 끌고 내려간다.
#>

param(
    [int]$IntervalMinutes = 10,
    [string]$TaskName = "ThinkwiseWikiSync"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $projectRoot "sync_index.ps1"
if (-not (Test-Path $script)) {
    throw "sync_index.ps1을 찾을 수 없습니다: $script"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $projectRoot

# 부팅 직후 한 번 돌고, 그 뒤로는 계속 반복한다.
# RepetitionDuration을 최대로 두어야 서버를 껐다 켜기 전까지 계속 반복한다.
$trigger = New-ScheduledTaskTrigger -AtStartup
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration ([TimeSpan]::MaxValue)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)   # 매달리면 다음 회차가 정리한다

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "등록 완료: $TaskName ($IntervalMinutes분마다)" -ForegroundColor Green
Write-Host "지금 한 번 돌리려면: Start-ScheduledTask -TaskName $TaskName"
Write-Host "로그:                 $projectRoot\logs\sync.log"
Write-Host ""
Write-Host "처음이라면 전체 적재를 먼저 하세요(53만행 기준 약 20초):" -ForegroundColor Yellow
Write-Host "  PowerShell -ExecutionPolicy Bypass -File .\sync_index.ps1 -Full"
