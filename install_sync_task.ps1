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

# 방아쇠 두 개를 건다.
#   ① 지금부터 $IntervalMinutes 마다 무기한 반복
#   ② 재부팅 직후 한 번 (색인이 며칠 낡은 채로 시작하지 않도록)
#
# 반복 기간(RepetitionDuration)은 일부러 주지 않는다. 비워 두면 작업 스케줄러가
# "무기한"으로 읽는다. [TimeSpan]::MaxValue를 주면 P99999999DT23H59M59S라는 값이
# 만들어지는데, 작업 스케줄러가 이 값을 범위를 벗어난 것으로 보고 등록을 거부한다.
$triggerRepeat = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$triggerBoot = New-ScheduledTaskTrigger -AtStartup
$trigger = @($triggerRepeat, $triggerBoot)

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
