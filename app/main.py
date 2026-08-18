from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response

from .index_db import IndexUnavailableError
from .models import BranchResponse, SearchResponse, SyncStatus
from .search_index import MAX_LIMIT, Filters, expand, search, sync_status


logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"

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
