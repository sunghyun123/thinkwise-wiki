$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    throw "가상환경이 없습니다. README.md의 최초 설치 절차를 먼저 진행해 주세요."
}

if (-not (Test-Path ".\.env")) {
    throw ".env 파일이 없습니다. .env.example을 복사해 DB 접속 정보를 입력해 주세요."
}

# 운영과 같은 액세스 로그를 보려고 여기서도 uvicorn 쪽을 끈다(run_server.ps1 주석 참고).
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log

