from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from .config import DatabaseSettings


# 운영 스키마에 실행되는 유일한 업무 SQL이다. 사용자 입력은 문자열 결합 없이
# 바인딩하며, 행 수는 API 상한보다 한 건만 더 읽어 다음 결과 유무만 확인한다.
SEARCH_SQL = """
SELECT
    w.c_date AS event_time,
    w.u_name AS author,
    w.gubun AS action_type,
    w.detail AS detail,
    b.TITLE AS collaboration
FROM tw_colla_log.work_log AS w
LEFT JOIN tw_colman.collaboration_board AS b
    ON b.HASHFNAME = w.hashfname
WHERE w.detail IS NOT NULL
  AND w.detail LIKE %s ESCAPE '!'
ORDER BY w.c_date DESC
LIMIT %s
""".strip()


def escape_like_literal(value: str) -> str:
    """LIKE의 특수문자를 일반 검색 문자로 취급한다."""

    return value.replace("!", "!!").replace("%", "!%").replace("_", "!_")


def _format_time(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return "" if value is None else str(value)


def search_work_logs(
    settings: DatabaseSettings, keyword: str, limit: int
) -> tuple[list[dict[str, str]], bool]:
    pattern = f"%{escape_like_literal(keyword)}%"
    connection = pymysql.connect(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password,
        charset="utf8mb4",
        cursorclass=DictCursor,
        connect_timeout=settings.connect_timeout,
        read_timeout=settings.read_timeout,
        write_timeout=settings.connect_timeout,
        autocommit=True,
    )

    try:
        with connection.cursor() as cursor:
            cursor.execute(SEARCH_SQL, (pattern, limit + 1))
            rows = cursor.fetchall()
    finally:
        connection.close()

    has_more = len(rows) > limit
    results = [
        {
            "event_time": _format_time(row.get("event_time")),
            "author": str(row.get("author") or ""),
            "action_type": str(row.get("action_type") or ""),
            "detail": str(row.get("detail") or ""),
            "collaboration": str(row.get("collaboration") or ""),
        }
        for row in rows[:limit]
    ]
    return results, has_more

