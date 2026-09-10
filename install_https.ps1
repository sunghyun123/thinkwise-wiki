#requires -RunAsAdministrator
<#
    wiki.yjsboard.com용 HTTPS 프록시를 준비한다.

    처음에는 -RegisterAcmeDns를 붙여 ACME-DNS 전용 자격증명을 생성한다.
    출력된 값을 사용해 DNS에 아래 두 레코드를 등록해야 실제 인증서 발급이 가능하다.
      wiki                    A       192.168.0.76
      _acme-challenge.wiki    CNAME   <acmedns-target.txt의 값>

    기본 실행은 설치와 작업 등록까지만 하고 서비스를 시작하지 않는다.
    DNS 전파를 확인한 뒤 -Start를 붙여 다시 실행한다.
#>

param(
    [string]$Hostname = "wiki.yjsboard.com",
    [string]$LanAddress = "192.168.0.76",
    [string]$Upstream = "127.0.0.1:8000",
    [string]$TaskName = "ThinkwiseWikiHttps",
    [switch]$RegisterAcmeDns,
    [switch]$Start
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$caddyDir = Join-Path $projectRoot "caddy"
$caddyExe = Join-Path $caddyDir "caddy.exe"
$caddyFile = Join-Path $caddyDir "Caddyfile"
$credentialFile = Join-Path $caddyDir "acmedns.json"
$targetFile = Join-Path $caddyDir "acmedns-target.txt"

New-Item -ItemType Directory -Force -Path $caddyDir | Out-Null

if ($RegisterAcmeDns -and -not (Test-Path -LiteralPath $credentialFile)) {
    $registration = Invoke-RestMethod `
        -Method Post `
        -Uri "https://auth.acme-dns.io/register" `
        -ContentType "application/json" `
        -Body "{}"

    $credentialJson = [ordered]@{
        username = $registration.username
        password = $registration.password
        subdomain = $registration.subdomain
        server_url = "https://auth.acme-dns.io"
    } | ConvertTo-Json

    [IO.File]::WriteAllText($credentialFile, $credentialJson, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($targetFile, $registration.fulldomain, [Text.UTF8Encoding]::new($false))
}

if (-not (Test-Path -LiteralPath $credentialFile)) {
    throw "ACME-DNS 자격증명 파일이 없습니다. -RegisterAcmeDns로 처음 한 번 생성하세요: $credentialFile"
}

$credential = Get-Content -Raw -LiteralPath $credentialFile | ConvertFrom-Json
foreach ($name in @("username", "password", "subdomain", "server_url")) {
    if (-not $credential.$name) {
        throw "ACME-DNS 자격증명에 '$name' 항목이 없습니다."
    }
}

if (-not (Test-Path -LiteralPath $targetFile)) {
    throw "ACME-DNS CNAME 대상 파일이 없습니다: $targetFile"
}
$cnameTarget = (Get-Content -Raw -LiteralPath $targetFile).Trim()
if (-not $cnameTarget.EndsWith(".auth.acme-dns.io")) {
    throw "ACME-DNS CNAME 대상 형식이 올바르지 않습니다: $cnameTarget"
}

# 갱신 키는 SYSTEM과 로컬 관리자만 읽을 수 있게 한다.
& icacls.exe $credentialFile /inheritance:r /grant:r '*S-1-5-18:(F)' '*S-1-5-32-544:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "ACME-DNS 자격증명 ACL 설정에 실패했습니다."
}

# DNS 플러그인이 포함된 공식 Caddy 맞춤 빌드다. 이미 올바른 바이너리가 있으면 다시 받지 않는다.
$needsDownload = $true
if (Test-Path -LiteralPath $caddyExe) {
    $modules = & $caddyExe list-modules 2>$null
    $needsDownload = $LASTEXITCODE -ne 0 -or $modules -notcontains "dns.providers.acmedns"
}

if ($needsDownload) {
    $downloadUrl = "https://caddyserver.com/api/download?os=windows&arch=amd64&p=github.com/caddy-dns/acmedns"
    $tempExe = Join-Path ([IO.Path]::GetTempPath()) ("thinkwise-caddy-{0}.exe" -f [guid]::NewGuid())
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $downloadUrl -OutFile $tempExe
        Unblock-File -LiteralPath $tempExe -ErrorAction SilentlyContinue
        $modules = & $tempExe list-modules 2>$null
        if ($LASTEXITCODE -ne 0 -or $modules -notcontains "dns.providers.acmedns") {
            throw "다운로드한 Caddy에 dns.providers.acmedns 모듈이 없습니다."
        }
        Move-Item -LiteralPath $tempExe -Destination $caddyExe -Force
    }
    finally {
        if (Test-Path -LiteralPath $tempExe) {
            Remove-Item -LiteralPath $tempExe -Force
        }
    }
}

$caddyPath = $caddyDir.Replace("\", "/")
$config = @"
{
    auto_https disable_redirects
    admin off
    log default {
        output file $caddyPath/runtime.log {
            roll_size 10MiB
            roll_keep 5
            roll_keep_for 720h
        }
        level INFO
    }
}

$Hostname {
    bind $LanAddress

    tls {
        dns acmedns $caddyPath/acmedns.json
        resolvers 1.1.1.1 8.8.8.8
    }

    reverse_proxy $Upstream
    encode zstd gzip

    header {
        Strict-Transport-Security "max-age=31536000"
    }

    log {
        output file $caddyPath/access.log {
            roll_size 10MiB
            roll_keep 5
            roll_keep_for 720h
        }
    }
}
"@

[IO.File]::WriteAllText($caddyFile, $config, [Text.UTF8Encoding]::new($false))
& $caddyExe fmt --overwrite $caddyFile
if ($LASTEXITCODE -ne 0) {
    throw "Caddy 설정 정리에 실패했습니다."
}
& $caddyExe validate --config $caddyFile --adapter caddyfile
if ($LASTEXITCODE -ne 0) {
    throw "Caddy 설정 검증에 실패했습니다."
}

$listeners = Get-NetTCPConnection -State Listen -LocalPort 443 -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalAddress -in @($LanAddress, "0.0.0.0", "::") }
$conflicts = $listeners | Where-Object {
    try {
        (Get-Process -Id $_.OwningProcess -ErrorAction Stop).Path -ne $caddyExe
    }
    catch {
        $true
    }
}
if ($conflicts) {
    $owners = $conflicts | Select-Object LocalAddress, OwningProcess | Format-Table -HideTableHeaders | Out-String
    throw "LAN 주소의 443 포트를 다른 프로세스가 사용 중입니다:`n$owners"
}

$action = New-ScheduledTaskAction `
    -Execute $caddyExe `
    -Argument "run --config `"$caddyFile`" --adapter caddyfile" `
    -WorkingDirectory $caddyDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

$firewallName = "Thinkwise Wiki HTTPS (LAN only)"
if (-not (Get-NetFirewallRule -DisplayName $firewallName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule `
        -DisplayName $firewallName `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalAddress $LanAddress `
        -LocalPort 443 `
        -RemoteAddress LocalSubnet | Out-Null
}

if ($Start) {
    $task = Get-ScheduledTask -TaskName $TaskName
    if ($task.State -eq "Running") {
        Stop-ScheduledTask -TaskName $TaskName
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            if ((Get-ScheduledTask -TaskName $TaskName).State -ne "Running") {
                break
            }
            Start-Sleep -Milliseconds 250
        }
        if ((Get-ScheduledTask -TaskName $TaskName).State -eq "Running") {
            throw "기존 HTTPS 작업이 종료되지 않아 새 설정으로 다시 시작하지 못했습니다."
        }
    }
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "HTTPS 프록시 시작 완료: https://$Hostname" -ForegroundColor Green
}
else {
    Write-Host "HTTPS 프록시 준비 완료(아직 시작하지 않음)" -ForegroundColor Green
}

Write-Host "가비아 A 레코드:       wiki -> $LanAddress"
Write-Host "가비아 CNAME 레코드:   _acme-challenge.wiki -> $cnameTarget"
Write-Host "DNS 확인 후 시작:      powershell -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`" -Start"
Write-Host "상태 확인:             Get-ScheduledTaskInfo -TaskName $TaskName"
Write-Host "런타임 로그:           $caddyDir\runtime.log"
