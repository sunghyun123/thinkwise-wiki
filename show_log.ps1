<#
    위키의 사용 로그를 보는 스크립트.

    왜 스크립트로 두는가: 따옴표나 파이프가 든 파워셸 명령을 SSH로 한 줄에 밀어 넣으면
    중간에 벗겨져 엉뚱하게 해석된다(deploy-windows.md 7단계). 서버에 스크립트를 두고
    이것만 부르면 붙여넣기용 명령이 짧고 안전해진다.

    사용 예 (개발 PC에서):
      ssh user@192.168.0.76 "powershell -ExecutionPolicy Bypass -File C:\apps\thinkwise-wiki\show_log.ps1"
      ssh user@192.168.0.76 "powershell -ExecutionPolicy Bypass -File C:\apps\thinkwise-wiki\show_log.ps1 -Search"
#>
param(
    # 보여줄 줄 수. -Follow 와 함께 쓰면 따라붙기 전에 보여줄 줄 수가 된다.
    [int]$Tail = 50,
    # 검색 요청만 본다(화면 열기·favicon·상태 확인을 걷어낸다).
    [switch]$Search,
    # 오늘 것만 본다.
    [switch]$Today,
    # 새 요청이 들어올 때마다 이어서 보여준다. Ctrl+C 로 끝낸다.
    [switch]$Follow,
    # 누가 얼마나 썼는지 집계한다.
    [switch]$Summary
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$logFile = Join-Path $projectRoot "logs\server.log"
if (-not (Test-Path $logFile)) {
    throw "로그 파일이 없습니다: $logFile  (서버가 한 번도 뜨지 않았을 수 있습니다)"
}

# 로그 파일에는 한글이 UTF-8로 온전히 들어 있고, 깨지는 곳은 '읽어서 내보내는' 경로다.
# SSH 로 부르면 콘솔이 cp949 라서 여기서 못 박아 둔다.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if ($Follow) {
    Get-Content $logFile -Wait -Tail $Tail -Encoding UTF8
    return
}

$lines = @(Get-Content $logFile -Encoding UTF8)

if ($Today) {
    $prefix = "[" + (Get-Date -Format "yyyy-MM-dd")
    $lines = @($lines | Where-Object { $_.StartsWith($prefix) })
}
if ($Search) {
    $lines = @($lines | Where-Object { $_ -like "*/api/search*" })
}

if (-not $Summary) {
    $lines | Select-Object -Last $Tail
    return
}

# 집계. 시각이 붙기 시작한 2026-08-20 이후 줄만 이 형식에 맞는다.
$pattern = "^\[(.+?)\] (\S+) (\S+) (.*) (\d{3}) (\d+)ms$"
$parsed = foreach ($line in $lines) {
    $m = [regex]::Match($line, $pattern)
    if ($m.Success) {
        [pscustomobject]@{
            시각   = $m.Groups[1].Value
            IP     = $m.Groups[2].Value
            주소   = $m.Groups[4].Value
            상태   = $m.Groups[5].Value
        }
    }
}

if (-not $parsed) {
    "집계할 줄이 없습니다. 시각이 붙은 로그는 2026-08-20 배포 이후 줄뿐입니다."
    return
}

"=== 접속 PC별 요청 수 ==="
$parsed | Group-Object IP | Sort-Object Count -Descending |
    Format-Table @{L="IP"; E={$_.Name}}, @{L="요청"; E={$_.Count}} -AutoSize

"=== 검색어 (최근 30건) ==="
$parsed | Where-Object { $_.주소 -like "/api/search*" } | Select-Object -Last 30 |
    ForEach-Object {
        # "/api/search?q=감리&limit=10" 에서 검색어만 꺼낸다.
        $q = ($_.주소 -replace "^.*[?&]q=", "") -replace "&.*$", ""
        "{0}  {1,-16} {2}" -f $_.시각, $_.IP, $q
    }

"=== 상태코드 ==="
$parsed | Group-Object 상태 | Sort-Object Count -Descending |
    Format-Table @{L="코드"; E={$_.Name}}, @{L="건수"; E={$_.Count}} -AutoSize
