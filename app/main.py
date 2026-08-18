from __future__ import annotations

import logging
from pathlib import Path

import pymysql
from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response

from .config import ConfigurationError, get_database_settings
from .db import search_work_logs
from .models import SearchResponse


logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="씽크와이즈 위키",
    description="씽크와이즈 작업 이력 읽기 전용 검색 MVP",
    version="0.1.0",
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


@app.get("/api/search", response_model=SearchResponse)
def search(
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
) -> SearchResponse:
    keyword = q.strip()
    if len(keyword) < 2:
        raise HTTPException(
            status_code=422,
            detail="검색어는 공백을 제외하고 2글자 이상 입력해 주세요.",
        )

    try:
        results, has_more = search_work_logs(
            get_database_settings(), keyword, limit
        )
    except ConfigurationError:
        logger.exception("데이터베이스 환경 설정 오류")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="데이터베이스 연결 설정을 확인해 주세요.",
        ) from None
    except pymysql.MySQLError:
        logger.exception("데이터베이스 검색 실패")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="데이터베이스 조회에 실패했습니다. 잠시 후 다시 시도해 주세요.",
        ) from None

    return SearchResponse(
        query=keyword,
        count=len(results),
        limit=limit,
        has_more=has_more,
        results=results,
    )
