param(
    # 색인을 처음부터 다시 만들 때만 붙인다. 평소에는 새로 생긴 것만 가져온다.
    [switch]$Full
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "가상환경이 없습니다. docs/deploy-windows.md의 설치 절차를 먼저 진행해 주세요."
}
if (-not (Test-Path (Join-Path $projectRoot ".env"))) {
    throw ".env 파일이 없습니다. .env.example을 복사해 DB 접속 정보를 입력해 주세요."
}

$logDir = Join-Path $projectRoot "logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}
$logFile = Join-Path $logDir "sync.log"

# 10분마다 도는 작업이라 로그가 계속 쌓인다. 한 세대만 보관한다.
if ((Test-Path $logFile) -and ((Get-Item $logFile).Length -gt 5MB)) {
    Move-Item $logFile "$logFile.old" -Force
}

# 파이썬과 파워셸이 서로 다른 글자표를 쓰면 로그의 한글이 깨진다. 양쪽을 UTF-8로 맞춘다.
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 여기부터는 Continue로 되돌린다. 설치 검사(python/.env 존재)는 이미 위에서 끝났다.
# 파워셸은 외부 프로그램이 표준 오류에 한 줄만 써도 그것을 '오류'로 포장하는데,
# 위쪽 Stop과 만나면 정상 진행 로그가 동기화를 죽인다(run_server.ps1에서 겪은 그 문제).
$ErrorActionPreference = "Continue"

# $args 는 파워셸이 이미 쓰는 이름이라 다른 이름을 쓴다.
$pyArgs = @("-m", "app.sync")
if ($Full) { $pyArgs += "--full" }

# "$_" 는 파워셸이 씌운 오류 포장을 벗겨 원래 로그 한 줄만 남긴다.
& $python @pyArgs 2>&1 | ForEach-Object { "$_" } | Out-File $logFile -Append -Encoding utf8

# 실패를 조용히 넘기면 색인이 낡은 채로 며칠이 간다.
# 종료 코드를 그대로 넘겨 작업 스케줄러의 '마지막 실행 결과'에 남게 한다.
if ($LASTEXITCODE -ne 0) {
    "동기화 실패 (종료 코드 $LASTEXITCODE) - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" |
        Out-File $logFile -Append -Encoding utf8
}
exit $LASTEXITCODE
