# 씽크와이즈 위키

씽크와이즈의 작업 이력을 검색하는 **개인용·읽기 전용 MVP**입니다. 검색 결과에는 시각, 작성자, 구분, 내용, 협업명이 표시되며 최신 작업부터 정렬됩니다.

## 현재 범위

- 접속 범위는 실행 방식으로 갈립니다. 개인 PC에서 `run_local.ps1`로 띄우면 `127.0.0.1`(그 PC 전용),
  사내 서버에서 `run_server.ps1`로 띄우면 `0.0.0.0`(사내망 공개)입니다. [사내 배포 절차](docs/deploy-windows.md)를 참고하세요.
- **로그인이 없습니다.** 사내 공개 시 URL을 아는 사람은 누구나 검색할 수 있으며, 접근 제한은 방화벽의 대역 제한뿐입니다.
- 검색어는 공백을 제외하고 최소 2글자, 최대 100글자입니다.
- 한 번에 20/50/100건을 선택하며 서버 상한은 100건입니다.
- 전체 건수 계산용 `COUNT` 쿼리를 실행하지 않습니다.
- 입력할 때마다 자동 검색하지 않고 검색 버튼을 눌렀을 때만 조회합니다.
- SQL은 파라미터 바인딩을 사용해 검색어를 쿼리에 직접 결합하지 않습니다.
- 애플리케이션 업무 SQL은 아래 두 테이블을 읽는 고정 `SELECT` 한 문장뿐입니다.
  - `tw_colla_log.work_log`
  - `tw_colman.collaboration_board`

> 중요한 안전 조건: 앱 코드가 읽기 전용이어도 DB 계정에 쓰기 권한이 있으면 운영 안전을 보장할 수 없습니다. 반드시 두 테이블에 대한 `SELECT` 권한만 가진 전용 계정을 사용하세요.

## 최초 설치 (Windows PowerShell)

Python 3.11 이상이 설치된 환경을 권장합니다. 아래 명령은 이 프로젝트 폴더에서 실행합니다.

```powershell
$python = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
& $python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env`를 메모장으로 열어 실제 MariaDB 접속 정보를 입력합니다.

```dotenv
DB_HOST=MariaDB서버주소
DB_PORT=3306
DB_USER=thinkwise_wiki_reader
DB_PASSWORD=전용계정비밀번호
DB_CONNECT_TIMEOUT=5
DB_READ_TIMEOUT=10
```

DB 전용 계정이 없다면 DBA에게 [docs/readonly-account.sql.example](docs/readonly-account.sql.example)을 전달하세요. 앱이 실행하는 파일이 아니며, DBA가 접속 허용 호스트와 비밀번호를 실제 값으로 바꿔 수동 적용하는 예시입니다.

## 실행

PowerShell에서 다음을 실행합니다.

```powershell
.\run_local.ps1
```

브라우저에서 <http://127.0.0.1:8000>을 엽니다. 종료할 때는 실행 중인 PowerShell 창에서 `Ctrl+C`를 누릅니다.

`run_local.ps1`에는 `--host 127.0.0.1`이 고정되어 있습니다. **이 파일은 개인 PC 전용이므로 여기를 `0.0.0.0`으로 바꾸지 마세요.**
사내에 공개할 때는 이 파일을 고치는 게 아니라 `run_server.ps1`을 씁니다. 두 실행 방식을 파일로 갈라 두어야
개인 PC에서 무심코 사내에 열리는 일이 생기지 않습니다.

## 사내 서버 구동

씽크와이즈 DB가 있는 PC에서 상시 구동해 사내 전체에 공개하는 절차는 [docs/deploy-windows.md](docs/deploy-windows.md)에 있습니다.
`run_server.ps1`(0.0.0.0 구동 + 파일 로그)과 `install_task.ps1`(재부팅 시 자동 시작 등록)을 사용합니다.

## 동작 확인

개발용 의존성을 설치하고 자동 테스트를 실행합니다. 테스트는 실제 MariaDB에 접속하지 않습니다.

```powershell
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
& .\.venv\Scripts\python.exe -m pytest
```

실제 DB 연결 확인은 앱을 실행한 뒤 두 글자 이상의 검색어로 한 번 조회하는 방식으로 진행합니다. 연결 정보나 DB 오류 원문은 브라우저에 노출하지 않습니다.

## DB 부하 관련 메모

현재 요구사항의 `LIKE '%검색어%'`는 일반 인덱스를 충분히 활용하지 못할 수 있습니다. 이 MVP는 개인 한 명의 수동 검색, 최소 글자 수, 최대 100건, 짧은 연결/읽기 제한으로 부하를 줄였습니다. `LIMIT`은 반환 행 수를 제한하지만 검색 과정의 전체 스캔 가능성까지 없애지는 않습니다.

운영 DB에는 인덱스 추가나 테이블 변경을 하지 않습니다. 검색이 느리거나 DB 부하가 확인되면 직원 전체 공개 전에 읽기 복제본 또는 별도 검색 인덱스를 검토해야 합니다.

## 파일 구성

```text
app/
  main.py              FastAPI 라우팅과 오류 처리
  db.py                고정 SELECT 및 MariaDB 연결
  config.py            .env 설정 로딩
  models.py            API 응답 형식
  static/index.html    단일 HTML/CSS/바닐라 JS 화면
docs/
  readonly-account.sql.example
  deploy-windows.md    사내 서버 배포 절차
tests/
run_local.ps1          개인 PC 실행 (127.0.0.1)
run_server.ps1         사내 서버 실행 (0.0.0.0 + 파일 로그)
install_task.ps1       재부팅 시 자동 시작 등록 (관리자 권한, 1회)
requirements.txt
```
