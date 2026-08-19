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
- `PrefixOrigin`이 `Dhcp`면 IP가 언젠가 바뀔 수 있습니다. 다만 **IP를 고정하지 않아도 됩니다** —
  사내 안내를 도메인(<http://wiki.yjselect.com:8000>)과 컴퓨터 이름(<http://DESKTOP-318VJ68:8000>)
  두 갈래로 하기 때문입니다. IP가 바뀌면 컴퓨터 이름 쪽은 윈도우가 알아서 따라가고,
  도메인 쪽은 `yjselect.com` DNS의 `wiki` A 레코드 값만 고치면 됩니다.
  6단계에서 실제로 되는지 확인합니다.

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

## 3.5 검색 색인 만들기

이 앱은 검색할 때 운영 DB를 조회하지 않고 **로컬 색인**에서만 찾습니다.
색인이 없으면 검색이 503으로 실패하므로 서버를 띄우기 전에 먼저 만듭니다.

```powershell
PowerShell -ExecutionPolicy Bypass -File .\sync_index.ps1 -Full
```

53만행 기준 약 20초 걸리고 `data\wiki_index.db`(약 105MB)가 생깁니다.
진행 상황은 `logs\sync.log`에 남습니다.

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

# 색인을 10분마다 최신으로 유지하는 별도 작업
.\install_sync_task.ps1
Start-ScheduledTask -TaskName ThinkwiseWikiSync
```

작업을 **둘로 나눈 이유**: 동기화가 실패해도 웹 서버는 그대로 떠서 검색이 계속 되어야 합니다.
한 프로세스에 묶으면 한쪽 사고가 다른 쪽을 끌고 내려갑니다.
색인이 낡으면 화면 오른쪽 위 배지가 노란색으로 바뀌어 사용자에게 알립니다.

확인:

```powershell
Get-ScheduledTask -TaskName ThinkwiseWiki | Get-ScheduledTaskInfo
Get-ScheduledTask -TaskName ThinkwiseWikiSync | Get-ScheduledTaskInfo
Get-NetTCPConnection -LocalPort 8000 -State Listen
```

이제 사내 다른 PC에서 접속됩니다. **반드시 서버가 아닌 다른 PC에서 확인하세요** —
여기까지의 점검은 전부 이 PC 안에서 이뤄져서, 방화벽과 `0.0.0.0`이 실제로 통하는지는
밖에서 붙어봐야만 알 수 있습니다.

- <http://wiki.yjselect.com:8000> — **메신저로 안내할 때는 이쪽.** 카톡 등에서 링크로 잡힙니다.
- <http://DESKTOP-318VJ68:8000> — IP가 바뀌어도 따라가는 예비 주소.
- <http://192.168.0.76:8000> — 위 둘이 다 안 되는 PC를 위한 최후 수단.

> **`:8000`을 빼면 안 됩니다.** 80번은 씽크와이즈 본체(IIS)라, 에러가 아니라 **씽크와이즈 협업플랫폼
> 로그인 화면이 200으로 정상적으로 뜹니다.** 받는 사람 눈에는 "위키가 씽크와이즈로 잘못 연결됐다"로 보입니다.
> **`https://`도 안 됩니다** — 이 서버는 평문 http만 서비스합니다.

이름 접속은 같은 네트워크 안의 윈도우 PC끼리 서로를 찾는 기능에 기대므로 100% 보장되지는 않습니다.
안 되는 PC가 나오면 그 PC에만 IP 주소를 알려주면 됩니다.

## 7. 원격 관리 (SSH) — 2026-08-18 추가

서버 PC에 가지 않고 **개발 PC(`192.168.0.78`)에서** 배포·재시작·로그 확인을 합니다.

설정은 끝나 있습니다. 아래는 무엇이 어떻게 되어 있는지의 기록입니다.

| 항목 | 값 |
| --- | --- |
| 접속 | `ssh user@192.168.0.76` (또는 `DESKTOP-318VJ68`) |
| 인증 | 개발 PC의 `~/.ssh/id_ed25519` 공개키 (암호 없음) |
| 서버의 키 파일 | `C:\ProgramData\ssh\administrators_authorized_keys` |
| 방화벽 | `OpenSSH-Server-In-TCP` → 모든 프로필 + `192.168.0.0/24`만 |
| GitHub 인증 | 저장소 **배포 키(읽기 전용)**, 서버 원격은 `git@github.com:...` |

설치할 때 밟은 함정 세 개를 남깁니다. 셋 다 **에러 없이 조용히 인증만 실패**합니다.

- **관리자 그룹 계정의 키는 개인 폴더(`~/.ssh/authorized_keys`)에 넣으면 무시됩니다.**
  윈도우 sshd 기본 설정이 관리자에 대해서만 `administrators_authorized_keys`를 보게 되어 있습니다.
- **키 파일에 BOM이 붙으면 sshd가 그 줄을 못 읽습니다.** `Out-File`·`Set-Content` 기본값이 BOM을 붙이므로
  `Add-Content -Encoding ascii`로 씁니다.
- **키 파일 권한이 넓으면 거부합니다.** 관리자·SYSTEM만 남깁니다.
  한글 윈도우는 그룹 이름이 다를 수 있어 이름 대신 SID로 지정합니다.
  `icacls <파일> /inheritance:r /grant "*S-1-5-32-544:F" /grant "*S-1-5-18:F"`

**`git pull`은 반드시 SSH 원격이어야 합니다.** HTTPS 원격이면 비공개 저장소 인증 창을 띄우려 하는데
SSH 세션에는 그 창(TTY)이 없어서 `could not read Username for 'https://github.com'`으로 실패합니다.
서버 원격은 배포 키를 쓰는 SSH 주소로 바꿔 두었습니다.

### 개발 PC에서 배포하기

```powershell
# 1) 코드 받기
ssh user@192.168.0.76 "cd /d C:\apps\thinkwise-wiki && git pull && git log --oneline -1"

# 2) 웹 서버만 재시작 (색인·동기화는 건드리지 않는다)
ssh user@192.168.0.76 "schtasks /end /tn ThinkwiseWiki & schtasks /run /tn ThinkwiseWiki"

# 3) 반드시 확인 — 2)가 반쪽만 성공해도 아무도 알려주지 않는다
ssh user@192.168.0.76 "netstat -ano | findstr LISTENING | findstr :8000"
```

> **3번을 생략하지 마세요.** 2026-08-18 배포에서 `Stop-ScheduledTask`는 성공하고
> `Start-ScheduledTask`가 실패해 **위키가 몇 분간 죽어 있었습니다.** 되살린 것은 `schtasks /run`입니다.
> `Start-ScheduledTask`가 그때 왜 "작업을 찾을 수 없다"고 했는지는 **원인을 확정하지 못했습니다**
> (지금은 같은 작업이 정상 조회됩니다). 그래서 위 표의 재시작 명령을 `schtasks`로 바꿨습니다.
> 색인 배지는 **색인의 나이만** 말해 주므로 서버가 죽은 것은 알려주지 않습니다.

`|`나 `"`가 들어간 PowerShell 명령을 SSH로 한 줄에 밀어 넣으면 따옴표가 중간에 벗겨져
엉뚱하게 해석됩니다. 여러 줄짜리 작업은 서버에 스크립트를 두고 그것을 호출하는 편이 낫습니다
(재시작 검증 스크립트는 아직 없습니다 — 아래 '아직 안 되어 있는 것' 참고).

## 운영 메모

| 하고 싶은 것 | 명령 |
| --- | --- |
| 서버 로그 보기 | `Get-Content C:\apps\thinkwise-wiki\logs\server.log -Tail 50 -Encoding UTF8` |
| 동기화 로그 보기 | `Get-Content C:\apps\thinkwise-wiki\logs\sync.log -Tail 50 -Encoding UTF8` |
| 재시작 | `schtasks /end /tn ThinkwiseWiki` → `schtasks /run /tn ThinkwiseWiki` → **8000번 확인** |
| 색인 지금 갱신 | `schtasks /run /tn ThinkwiseWikiSync` |
| 색인 처음부터 다시 | `PowerShell -ExecutionPolicy Bypass -File .\sync_index.ps1 -Full` |
| 코드 업데이트 | 위 7단계 '개발 PC에서 배포하기' 3줄 |
| 등록 해제 | `Unregister-ScheduledTask -TaskName ThinkwiseWiki -Confirm:$false`<br>`Unregister-ScheduledTask -TaskName ThinkwiseWikiSync -Confirm:$false` |
| 방화벽 되돌리기 | `Remove-NetFirewallRule -DisplayName "Thinkwise Wiki 8000"` |
| **씽크와이즈 로그인이 뜬다고 할 때** | 주소에서 `:8000`이 빠진 것. 80번은 씽크와이즈 본체다 |
| **도메인으로 안 들어가진다고 할 때** | 먼저 `DESKTOP-318VJ68:8000`으로 되는지 확인 → 되면 **IP가 바뀐 것**.<br>`yjselect.com` DNS의 `wiki` A 레코드를 새 IP로 고친다 |

## 아직 안 되어 있는 것

- **로그인이 없습니다.** 사내망에서 URL을 아는 사람은 누구나 전 직원의 작업 이력을 검색할 수 있습니다.
  현재 접근 제한은 5단계 방화벽 규칙의 대역 제한뿐입니다.
- **과거 행이 수정·삭제되면 따라가지 못합니다.** 증분 복제는 `indx`가 커지는 것만 봅니다.
  감사 로그라 과거가 바뀔 일이 없어 보이지만 **확인한 사실은 아닙니다.**
  이상하면 `sync_index.ps1 -Full`로 다시 만들면 됩니다.
- **재부팅 후 자동 시작을 아직 실제로 확인하지 않았습니다**(등록만 확인).
- **도메인은 IP가 바뀌면 조용히 죽습니다.** `wiki.yjselect.com`의 A 레코드에 `192.168.0.76`을
  손으로 적어 둔 것이라, 공유기가 다른 IP를 할당하는 날 링크가 안 열리고 **아무도 알려주지 않습니다.**
  예비 주소(컴퓨터 이름)를 남겨 둔 것이 이때의 진단 수단입니다.
- **이 도메인의 수명은 우리 손에 없습니다.** `yjselect.com`이 지금은 `includeSubDomains` 없이
  HSTS를 보내지만, 회사 홈페이지 쪽에서 그 한 조각을 **추가하는 순간 위키가 조용히 죽습니다**
  (브라우저가 https로 승격시켜 연결이 실패하고, 우리 서버 로그에는 아무것도 안 남습니다).
  `yjsboard.com`에서 오늘 겪은 것이 정확히 그 상태입니다. 우리가 통제하지 못하는 설정에 얹혀 있습니다.
- **사내 IP가 공개 DNS에 드러납니다.** 인터넷의 누구나 `wiki.yjselect.com`을 조회해
  `192.168.0.76`을 알 수 있습니다. 사설 IP라 밖에서 닿지는 못하지만, 사내망 대역과 서버 위치를
  알려주는 셈입니다. 임시 시스템이라 감수한 것입니다.
- **https가 없습니다.** 주소를 손으로 칠 때 `https://`를 붙이면 연결이 실패합니다.
  사설 IP를 가리키는 도메인이라 인증서에 DNS 챌린지가 필요하고, 자동 갱신을 붙이지 않으면
  90일마다 손이 갑니다. 임시 시스템이라 달지 않기로 한 것입니다.
