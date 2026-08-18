param(
    # 8000번을 다른 프로그램이 쓰게 되면 이 값만 바꾸면 된다.
    [int]$Port = 8000
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

# 작업 스케줄러로 돌면 콘솔이 없어 오류를 볼 수 없다. 파일로 남긴다.
$logDir = Join-Path $projectRoot "logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}
$logFile = Join-Path $logDir "server.log"

# 서버가 몇 달씩 붙어 있으므로 시작할 때마다 크기를 확인해 한 세대만 보관한다.
if ((Test-Path $logFile) -and ((Get-Item $logFile).Length -gt 10MB)) {
    Move-Item $logFile "$logFile.old" -Force
}

"=== 시작: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') / 포트 $Port ===" | Out-File $logFile -Append -Encoding utf8

# run_local.ps1과 갈리는 유일한 지점: 127.0.0.1이 아니라 0.0.0.0에 연다.
# 127.0.0.1은 이 PC 자신만 접속 가능해서 사내 다른 PC가 못 붙는다.
& $python -m uvicorn app.main:app --host 0.0.0.0 --port $Port *>> $logFile
