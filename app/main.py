from __future__ import annotations

import logging
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import unquote, unquote_plus

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response

from .index_db import IndexUnavailableError
from .models import BranchResponse, SearchResponse, SyncStatus
from .search_index import MAX_LIMIT, Filters, expand, search, sync_status


logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"

# 사람이 읽을 수 있는 액세스 로그를 여기서 직접 남긴다(uvicorn 것은 --no-access-log로 끈다).
# uvicorn 기본 포맷에는 시각이 없고 주소가 %인코딩된 채라, 누가 언제 무엇을 찾았는지
# 로그만 보고는 알 수 없었다. 이 앱의 유일한 사용 기록이 이것뿐이라 읽히는 게 중요하다.
access_logger = logging.getLogger("app.access")
ACCESS_TARGET_LIMIT = 300


def _configure_access_logger() -> None:
    """uvicorn의 로깅 설정은 root 로거를 건드리지 않는다. 그래서 핸들러를 손수 붙이지
    않으면 이 로거의 info는 에러 없이 그냥 사라진다."""

    if access_logger.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    # 시각은 이 PC의 시계를 그대로 읽는다(sync.py의 로그와 같은 규칙이라 두 로그를
    # 나란히 놓고 볼 수 있다). 서버가 한국 시간으로 맞춰져 있다는 전제이고,
    # 코드가 보장하는 값이 아니다.
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    access_logger.addHandler(handler)
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False


_configure_access_logger()


def _readable(path: str, query: str) -> str:
    """요청 주소를 로그 한 줄에 담을 수 있게 다듬는다.

    %인코딩을 풀어 검색어를 사람이 읽게 하되, 푼 값은 사용자가 보낸 문자열이라
    줄바꿈이 섞여 있을 수 있다. 그대로 두면 %0A 하나로 로그에 가짜 줄을 끼워 넣을 수
    있는데, 로그는 나중에 사람이 읽고 판단하는 근거라 위조되면 안 된다.

    경로와 쿼리를 나눠 푸는 이유: 화면이 URLSearchParams로 주소를 만들어서 검색어의
    공백이 "+"로 온다("오늘 한일" -> "오늘+한일"). 쿼리 쪽만 그 규칙으로 풀어야 하고,
    경로에 들어온 "+"는 글자 그대로여서 같이 풀면 없는 공백이 생긴다.
    """

    text = unquote(path)
    if query:
        text += "?" + unquote_plus(query)
    text = "".join(ch if ch.isprintable() else " " for ch in text)
    if len(text) > ACCESS_TARGET_LIMIT:
        text = text[:ACCESS_TARGET_LIMIT] + "...(잘림)"
    return text


app = FastAPI(
    title="씽크와이즈 위키",
    description="씽크와이즈 작업 이력 읽기 전용 검색",
    version="0.2.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.middleware("http")
async def write_access_log(request: Request, call_next) -> Response:
    started = time.perf_counter()
    # 핸들러가 예외로 끝나면 응답 객체가 없다. 그때 사용자가 실제로 받는 것은 500이다.
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        # 기록하다 터져도 요청은 살아야 한다. logging은 핸들러에서 난 예외를
        # 삼키므로(print는 안 삼킨다) 로그 실패가 응답 실패로 둔갑하지 않는다.
        access_logger.info(
            "%s %s %s %s %dms",
            request.client.host if request.client else "-",
            request.method,
            _readable(request.url.path, request.url.query),
            status_code,
            int((time.perf_counter() - started) * 1000),
        )


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _guard(exc: Exception) -> HTTPException:
    """색인 쪽 실패를 사용자에게 보여줄 말로 바꾼다. 내부 경로는 노출하지 않는다."""

    if isinstance(exc, IndexUnavailableError):
        logger.error("검색 색인 없음: %s", exc)
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="검색 색인이 아직 준비되지 않았습니다. 관리자에게 알려 주세요.",
        )
    logger.exception("검색 색인 조회 실패")
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="검색에 실패했습니다. 잠시 후 다시 시도해 주세요.",
    )


@app.get("/api/search", response_model=SearchResponse)
def search_api(
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    year: str = Query(default="", max_length=4),
    map: str = Query(default="", max_length=500),
    author: str = Query(default="", max_length=100),
) -> SearchResponse:
    keyword = q.strip()
    if len(keyword) < 2:
        raise HTTPException(
            status_code=422,
            detail="검색어는 공백을 제외하고 2글자 이상 입력해 주세요.",
        )

    try:
        payload = search(
            keyword, limit, Filters(year=year.strip(), collaboration=map, author=author)
        )
    except (IndexUnavailableError, sqlite3.Error) as exc:
        raise _guard(exc) from None

    return SearchResponse(query=keyword, **payload)


@app.get("/api/branch/{branch_id}", response_model=BranchResponse)
def branch_api(branch_id: int) -> BranchResponse:
    """접힌 한 줄을 펼쳐 원본 작업 기록을 보여준다.

    접기를 저장하지 않고 검색할 때 파생시켰기 때문에, 원본 이벤트가 색인에 그대로
    남아 있어 여기서 운영 DB를 다시 부를 일이 없다.
    """

    try:
        payload = expand(branch_id)
    except (IndexUnavailableError, sqlite3.Error) as exc:
        raise _guard(exc) from None

    if not payload:
        raise HTTPException(status_code=404, detail="해당 가지를 찾을 수 없습니다.")
    return BranchResponse(**payload)


@app.get("/api/status", response_model=SyncStatus)
def status_api() -> SyncStatus:
    try:
        return SyncStatus(**sync_status())
    except (IndexUnavailableError, sqlite3.Error) as exc:
        raise _guard(exc) from None
