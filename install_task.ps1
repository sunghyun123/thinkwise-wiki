#requires -RunAsAdministrator
<#
    서버 PC에서 한 번만 실행한다. 재부팅되어도 위키가 자동으로 다시 뜨게 만든다.
    씽크와이즈와 MySQL은 서비스로 등록되어 있어 알아서 살아나지만,
    이 앱은 등록해 두지 않으면 다음 윈도우 업데이트 재부팅 때 조용히 죽은 채로 남는다.
#>

param(
    [int]$Port = 8000,
    [string]$TaskName = "ThinkwiseWiki"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $projectRoot "run_server.ps1"
if (-not (Test-Path $script)) {
    throw "run_server.ps1을 찾을 수 없습니다: $script"
}

# 파이썬이 C:\Users\user\AppData\... 에 설치되어 있어 SYSTEM 계정의 PATH에는 없다.
# run_server.ps1이 .venv 안의 python.exe를 절대 경로로 부르므로 PATH에 의존하지 않는다.
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -Port $Port" `
    -WorkingDirectory $projectRoot

$trigger = New-ScheduledTaskTrigger -AtStartup

$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)   # 서버는 계속 떠 있어야 하므로 시간 제한 없음

# 로그인하지 않아도 떠 있어야 하므로 SYSTEM 계정으로 돌린다.
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "등록 완료: $TaskName (포트 $Port)" -ForegroundColor Green
Write-Host "지금 바로 시작하려면: Start-ScheduledTask -TaskName $TaskName"
Write-Host "상태 확인:            Get-ScheduledTask -TaskName $TaskName"
Write-Host "로그:                 $projectRoot\logs\server.log"
