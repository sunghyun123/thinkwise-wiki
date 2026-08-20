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
    -Protocol TCP -LocalPort 8000 -Action Allow -Profile Any `
    -RemoteAddress 192.168.0.0/24
```

- `-RemoteAddress 192.168.0.0/24` — 사내 대역에서 오는 요청만 받습니다.
  앱에 로그인이 없으므로 **이 한 줄이 현재 유일한 접근 제한입니다.**
- `-Profile Any` — 프로필로는 제한하지 않습니다. 2026-08-19까지 이 문서는 `Private,Domain`으로
  적어 두었지만 **그대로 하면 사내에서 위키가 열리지 않습니다.** 이 PC의 이더넷은 네트워크
  범주가 `Public`이라(`Get-NetConnectionProfile`으로 확인) `Private,Domain` 규칙이 그 인터페이스에
  적용되지 않습니다. 실제로 등록되어 있는 규칙도 `Any`입니다(2026-08-20 실측).
- 그래서 남는 대가: 이 PC가 다른 네트워크에 붙어도 규칙은 그대로 살아 있고, 그때 막아 주는 것은
  대역 제한 하나뿐입니다. **`192.168.0.0/24`는 어느 회사에나 어느 집에나 있는 대역**이라
  "사내"를 가리키는 표시가 아닙니다(2026-08-19에 사설 IP로 배운 것과 같은 성질입니다).
- 파일 공유(445번)는 열려 있지 않습니다 — 개발 PC에서 도달 실패, 445를 허용하는 인바운드 규칙
  없음(2026-08-20 실측). 그래서 윈도우 기본 관리 공유(`C$`)로 서버의 파일을 네트워크에서
  읽어가는 경로는 닫혀 있습니다.

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

> **2026-08-20 확인: 지금 색인을 돌리는 것은 이 작업이 아닙니다.** `ThinkwiseWikiSync`는
> `Disabled` 상태이고, 실제로는 `YJS ThinkWise Shared Index Sync`라는 별도 작업이
> `C:\apps\yjs_backoffice\scripts\run_thinkwise_index_sync.ps1 -WikiRoot C:\apps\thinkwise-wiki`를
> **60초마다** 실행하고 있습니다. 그쪽은 `sync_index.ps1`을 거치지 않으므로
> **`logs\sync.log`에 한 줄도 남지 않습니다** — 그 파일은 2026-08-19 10:30에서 멈춰 있어서,
> 그것만 보고 "동기화가 며칠째 죽었다"고 오진하기 쉽습니다. 색인이 실제로 최신인지는
> `sync.log`가 아니라 **`/api/status`의 `age_minutes`**로 판단하세요.

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
| 누가 무엇을 검색했나 | `Select-String C:\apps\thinkwise-wiki\logs\server.log -Pattern '/api/search' -Encoding UTF8 \| Select-Object -Last 50` |
| 동기화 로그 보기 | `sync.log`는 2026-08-19 이후 갱신되지 않습니다(6단계 주의 참고). 색인의 나이는<br>`(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/status).Content` |
| 재시작 | `schtasks /end /tn ThinkwiseWiki` → `schtasks /run /tn ThinkwiseWiki` → **8000번 확인** |
| 색인 지금 갱신 | `schtasks /run /tn ThinkwiseWikiSync` |
| 색인 처음부터 다시 | `PowerShell -ExecutionPolicy Bypass -File .\sync_index.ps1 -Full` |
| 코드 업데이트 | 위 7단계 '개발 PC에서 배포하기' 3줄 |
| 등록 해제 | `Unregister-ScheduledTask -TaskName ThinkwiseWiki -Confirm:$false`<br>`Unregister-ScheduledTask -TaskName ThinkwiseWikiSync -Confirm:$false` |
| 방화벽 되돌리기 | `Remove-NetFirewallRule -DisplayName "Thinkwise Wiki 8000"` |
| **씽크와이즈 로그인이 뜬다고 할 때** | 주소에서 `:8000`이 빠진 것. 80번은 씽크와이즈 본체다 |
| **도메인으로 안 들어가진다고 할 때** | 먼저 `DESKTOP-318VJ68:8000`으로 되는지 확인 → 되면 **IP가 바뀐 것**.<br>`yjselect.com` DNS의 `wiki` A 레코드를 새 IP로 고친다 |

### 사용 로그 (누가 언제 무엇을 검색했나)

`server.log`에 요청 한 건이 한 줄씩 쌓입니다(2026-08-20부터 이 형식입니다).

```
[2026-08-20 11:39:48] 192.168.0.78 GET /api/search?q=오늘 한일&limit=10 200 118ms
```

시각·접속 PC·검색어·상태코드·소요 시간입니다. 검색어는 `%`인코딩을 풀어서 남기므로
그대로 읽힙니다. 이 로그는 `app/main.py`가 직접 남기고, uvicorn 자체 액세스 로그는
`run_server.ps1`의 `--no-access-log`로 꺼 두었습니다(안 끄면 같은 요청이 두 줄씩 쌓입니다).

개발 PC에서 조회할 때는 `show_log.ps1`을 부릅니다. 서버에 스크립트를 두는 이유는
7단계에 적은 그것입니다 — 따옴표나 `|`가 든 파워셸 명령을 SSH로 한 줄에 밀어 넣으면
중간에 벗겨져 엉뚱하게 해석됩니다.

```powershell
# 최근 50줄
ssh user@192.168.0.76 "powershell -ExecutionPolicy Bypass -File C:\apps\thinkwise-wiki\show_log.ps1"

# 검색 요청만 (화면 열기·favicon·상태 확인을 걷어낸다)
ssh user@192.168.0.76 "powershell -ExecutionPolicy Bypass -File C:\apps\thinkwise-wiki\show_log.ps1 -Search"

# 오늘 것만
ssh user@192.168.0.76 "powershell -ExecutionPolicy Bypass -File C:\apps\thinkwise-wiki\show_log.ps1 -Today"

# 누가 얼마나 썼나 (접속 PC별 요청 수 + 검색어 + 상태코드)
ssh user@192.168.0.76 "powershell -ExecutionPolicy Bypass -File C:\apps\thinkwise-wiki\show_log.ps1 -Summary"

# 실시간으로 따라보기 (Ctrl+C 로 끝냄)
ssh user@192.168.0.76 "powershell -ExecutionPolicy Bypass -File C:\apps\thinkwise-wiki\show_log.ps1 -Follow"
```

> **스크립트가 `[Console]::OutputEncoding`을 UTF-8로 못 박아 둡니다. 이게 없으면 한글이
> 깨져서 옵니다.** 파일에는 UTF-8로 온전히 저장되어 있고 깨지는 곳은 SSH로 **읽어내는**
> 경로입니다(서버 쪽 콘솔이 cp949). 글자가 깨졌을 때 저장이 잘못된 것인지 읽기가
> 잘못된 것인지를 먼저 갈라야 하는 이유입니다.

로그 회전은 `run_server.ps1`이 **서버를 기동할 때만** 검사합니다(10MB 넘으면 `.old`로 밀어냄).
서버가 몇 달 붙어 있으면 검사할 기회 자체가 없습니다 — 현재 증가 속도로는 몇 년치 여유가
있지만, "회전이 걸려 있다"는 말은 정확하지 않습니다.

## 아직 안 되어 있는 것

- **로그인이 없습니다.** 사내망에서 URL을 아는 사람은 누구나 전 직원의 작업 이력을 검색할 수 있습니다.
  현재 접근 제한은 5단계 방화벽 규칙의 대역 제한뿐입니다.
- **사용 로그에 "누가 언제 무엇을 찾았는지"가 남습니다.** 로그인이 없으니 IP가 사실상
  사람을 가리키고, 검색어에는 사람 이름이나 인사 관련 낱말이 들어옵니다. 지금은 그 파일에
  닿을 수 있는 문이 SSH(개발 PC의 키)와 서버 PC 앞뿐이고 활성 계정도 하나뿐이라
  관리자만 읽을 수 있는 상태입니다 — 다만 그것을 보장하는 건 코드가 아니라 **그 PC의
  계정·권한 설정**입니다. 계정을 늘리거나 공유 폴더를 열면 그날 이 성질이 바뀝니다.
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
