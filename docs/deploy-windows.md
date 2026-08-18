# 사내 서버 배포 (Windows)

씽크와이즈 DB가 있는 PC(`192.168.0.76` / `DESKTOP-318VJ68`)에서 이 앱을 상시 구동해
사내 다른 PC에서 접속할 수 있게 하는 절차입니다. **서버 PC에서** 실행합니다.

전제: 그 PC에 Python 3.11, MySQL(Running), 8000번 포트 여유가 확인되어 있습니다.

## 0. 현재 상태 확인

```powershell
Get-Command git -ErrorAction SilentlyContinue | Select Source
Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "이더넷" | Select IPAddress, PrefixOrigin
```

- `git`이 없으면 <https://git-scm.com/download/win> 에서 설치합니다.
- `PrefixOrigin`이 `Dhcp`면 IP가 언젠가 바뀔 수 있습니다. 공유기에서 고정(DHCP 예약)하거나
  수동 IP로 바꿔야 사내 링크가 죽지 않습니다. `Manual`이면 그대로 두면 됩니다.

## 1. 코드 내려받기

사용자 프로필 아래가 아니라 별도 폴더에 둡니다. 작업 스케줄러가 SYSTEM 계정으로 실행하기 때문에
`C:\Users\...` 아래에 두면 권한이 얽히기 쉽습니다.

```powershell
New-Item -ItemType Directory -Path C:\apps -Force
Set-Location C:\apps
git clone https://github.com/sunghyun123/thinkwise-wiki.git
Set-Location C:\apps\thinkwise-wiki
```

비공개 저장소라 로그인 창이 한 번 뜹니다. 브라우저에서 GitHub 계정으로 승인하면 됩니다.

## 2. 가상환경과 의존성

```powershell
$python = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
& $python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 3. `.env` 작성

`.env`는 저장소에 올라가지 않습니다. 직접 만듭니다.

```powershell
Copy-Item .env.example .env
notepad .env
```

DB 접속 정보를 실제 값으로 채웁니다.

> `DB_HOST`를 `127.0.0.1`로 바꾸지 마세요. MySQL 계정 권한은 아이디뿐 아니라
> **접속해 오는 주소까지 묶어서** 부여됩니다. 계정이 `'tw_ro'@'192.168.0.%'`로 만들어져 있으면
> 같은 PC에서도 `127.0.0.1`로 접속하는 순간 다른 사용자 취급을 받아 로그인이 거부됩니다.
> 지금 동작하는 주소를 그대로 씁니다.

## 4. 손으로 한 번 띄워 확인

자동 등록 전에 수동으로 떠는지 먼저 봅니다.

```powershell
PowerShell -ExecutionPolicy Bypass -File .\run_server.ps1
```

윈도우는 기본적으로 직접 만든 `.ps1` 파일의 실행을 막습니다. `-ExecutionPolicy Bypass`는
**이번 실행에서만** 그 검사를 건너뛰라는 뜻이며 시스템 설정을 바꾸지 않습니다.
(6단계의 자동 시작은 등록 명령에 이미 이 옵션이 들어 있어 이 문제를 겪지 않습니다.)

띄우면 **콘솔에는 아무것도 나오지 않는 것이 정상입니다.** 서버 출력은 전부 `logs\server.log`로 갑니다.

같은 PC에서 <http://127.0.0.1:8000> 을 열어 두 글자 이상으로 검색해 봅니다.
결과가 나오면 `Ctrl+C`로 종료하고 다음 단계로 갑니다.

실패하면 로그를 확인합니다.

```powershell
Get-Content .\logs\server.log -Tail 30 -Encoding UTF8
```

## 5. 방화벽 열기

여기까지는 이 PC 안에서만 접속됩니다. 사내 다른 PC가 붙으려면 방화벽에 구멍이 필요합니다.
**관리자 권한 PowerShell**에서 실행합니다.

```powershell
New-NetFirewallRule -DisplayName "Thinkwise Wiki 8000" -Direction Inbound `
    -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private,Domain `
    -RemoteAddress 192.168.0.0/24
```

- `-Profile Private,Domain` — 공용 네트워크 프로필에서는 열지 않습니다.
- `-RemoteAddress 192.168.0.0/24` — 사내 대역에서 오는 요청만 받습니다.
  앱에 로그인이 없으므로 이 두 줄이 현재 유일한 접근 제한입니다.

## 6. 자동 시작 등록

**관리자 권한 PowerShell**에서 한 번만 실행합니다.

```powershell
.\install_task.ps1
Start-ScheduledTask -TaskName ThinkwiseWiki
```

확인:

```powershell
Get-ScheduledTask -TaskName ThinkwiseWiki | Get-ScheduledTaskInfo
Get-NetTCPConnection -LocalPort 8000 -State Listen
```

이제 사내 다른 PC에서 <http://192.168.0.76:8000> 으로 접속됩니다.

## 운영 메모

| 하고 싶은 것 | 명령 |
| --- | --- |
| 로그 보기 | `Get-Content C:\apps\thinkwise-wiki\logs\server.log -Tail 50 -Encoding UTF8` |
| 재시작 | `Stop-ScheduledTask -TaskName ThinkwiseWiki; Start-ScheduledTask -TaskName ThinkwiseWiki` |
| 코드 업데이트 | `git pull` 후 위 재시작 |
| 등록 해제 | `Unregister-ScheduledTask -TaskName ThinkwiseWiki -Confirm:$false` |
| 방화벽 되돌리기 | `Remove-NetFirewallRule -DisplayName "Thinkwise Wiki 8000"` |

## 아직 안 되어 있는 것

- **로그인이 없습니다.** 사내망에서 URL을 아는 사람은 누구나 전 직원의 작업 이력을 검색할 수 있습니다.
  현재 접근 제한은 5단계 방화벽 규칙의 대역 제한뿐입니다.
- **DB 부하 대비가 없습니다.** 검색이 `LIKE '%검색어%'`라 인덱스를 타지 못하고 전체 스캔이 될 수 있습니다.
  혼자 쓸 때는 문제가 없었지만 여러 명이 동시에 검색하면 운영 DB에 부담이 갑니다.
  느려지는 게 확인되면 읽기 복제본이나 별도 검색 인덱스를 검토해야 합니다.
