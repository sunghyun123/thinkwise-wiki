"""로컬 색인에서 검색한다. 운영 MariaDB에는 접근하지 않는다.

검색 한 번의 실측(53만행 색인):
    '공사'  100건 220ms / 1000건 234ms      (운영 MariaDB 같은 검색 663ms)
    '배관'   96ms,  없는 단어 92ms
LIMIT을 10배로 늘려도 14ms 차이라, "몇 건 보여줄까"는 이제 성능이 아니라 화면 문제다.

접기(같은 협업 + 같은 내용의 반복 이벤트 합치기)는 저장하지 않고 여기서 파생시킨다.
저장하면 새 이벤트가 들어올 때마다 요약을 갱신해야 하고, 한 경로만 빠뜨려도 영구히
어긋난다. 파생시키면 규칙을 바꿔도 53만행 재적재가 필요 없다.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .index_db import connect, get_state


MAX_LIMIT = 500


def escape_like_literal(value: str) -> str:
    """LIKE의 특수문자를 일반 검색 문자로 취급한다."""

    return value.replace("!", "!!").replace("%", "!%").replace("_", "!_")


# 접기와 요약을 한 번에 만드는 공통 부분.
#
#  last_real_indx  : '이동의 부산물'이 아닌 마지막 이벤트. 삭제 판정에 쓴다.
#                    이걸 안 쓰고 그냥 마지막 이벤트로 판정하면, 씽크와이즈가 이동할 때
#                    남기는 DEL 때문에 멀쩡한 가지 18,197개에 '삭제됨'이 붙는다(실측).
#  last_named_indx : 이름이 있는 마지막 이벤트. 작성자가 빈 행이 12.1%라,
#                    하필 마지막 행이 빈칸이면 작성자가 통째로 사라진다.
FOLD_CTE = """
WITH fold AS (
    SELECT hashfname,
           detail,
           COUNT(*)                                   AS event_count,
           MIN(c_date)                                AS first_at,
           MAX(indx)                                  AS last_indx,
           MAX(CASE WHEN move_pair = 0 THEN indx END) AS last_real_indx,
           MAX(CASE WHEN u_name <> ''  THEN indx END) AS last_named_indx,
           GROUP_CONCAT(DISTINCT gubun)               AS kinds
    FROM work_log
    WHERE detail LIKE :pattern ESCAPE '!'
    GROUP BY hashfname, detail
),
enriched AS (
    SELECT f.hashfname,
           f.detail,
           f.event_count,
           f.first_at,
           f.last_indx,
           f.kinds,
           r.c_date                AS last_at,
           r.gubun                 AS last_gubun,
           COALESCE(nm.u_name, '') AS last_author,
           COALESCE(c.title,   '') AS collaboration,
           substr(r.c_date, 1, 4)  AS last_year
    FROM fold f
    -- last_real_indx가 비는 경우는 없지만, 비면 요약이 통째로 사라지므로 받쳐 둔다.
    LEFT JOIN work_log     r  ON r.indx  = COALESCE(f.last_real_indx, f.last_indx)
    LEFT JOIN work_log     nm ON nm.indx = f.last_named_indx
    LEFT JOIN collaboration c ON c.hashfname = f.hashfname
)
"""


@dataclass(frozen=True)
class Filters:
    year: str = ""
    collaboration: str = ""
    author: str = ""

    def where(self, exclude: str = "") -> tuple[str, dict[str, Any]]:
        """필터를 SQL 조건으로 바꾼다. 값은 전부 바인딩한다(문자열 결합 금지).

        exclude: 이 필터 하나만 빼고 조건을 만든다.

        선택지 목록(패싯)을 만들 때 자기 자신은 빼야 한다. 안 그러면 2021년을 고른
        순간 연도 목록에 2021만 남아서, 드롭다운이 '연도를 바꾸는 도구'로서 죽는다.
        선택지는 현재 선택이 아니라 검색어 전체에서 파생시킨다.
        """

        clauses: list[str] = []
        params: dict[str, Any] = {}
        if self.year and exclude != "year":
            clauses.append("last_year = :f_year")
            params["f_year"] = self.year
        if self.collaboration and exclude != "map":
            clauses.append("collaboration = :f_collab")
            params["f_collab"] = self.collaboration
        if self.author and exclude != "author":
            clauses.append("last_author = :f_author")
            params["f_author"] = self.author
        return (" AND ".join(clauses) if clauses else "1=1"), params


# 접기 결과를 임시 테이블에 한 번만 만든다.
#
# 목록과 개수·패싯을 각각 별도 쿼리로 뽑으면 같은 접기를 두 번 계산하게 되고,
# 실측으로 '공사' 검색이 790ms까지 올라갔다. 한 번만 접어 두고 그 위에서 세면 307ms다
# (접기 279ms + 목록·집계 28ms). 접기 자체가 비용의 거의 전부라서, 집계를 몇 개 더
# 붙이는 건 사실상 공짜다.
#
# 읽기 전용 연결에서도 임시 테이블은 만들 수 있다. 임시 테이블은 색인 파일이 아니라
# 별도의 임시 DB에 살기 때문이다. 연결은 요청마다 새로 열고 닫으므로 뒷정리도 필요 없다.
BUILD_HITS_SQL = FOLD_CTE + """
SELECT * FROM enriched
"""

# 접힌 한 줄을 펼친다. 접기를 저장하지 않았기 때문에 원본 이벤트가 그대로 남아 있어
# GROUP BY만 빼면 되고, 운영 DB를 다시 부르지 않는다.
EXPAND_SQL = """
SELECT w.indx, w.c_date, w.u_name, w.gubun, w.move_pair
FROM work_log w
WHERE w.hashfname = (SELECT hashfname FROM work_log WHERE indx = :indx)
  AND w.detail IS (SELECT detail FROM work_log WHERE indx = :indx)
ORDER BY w.indx DESC
LIMIT :limit
"""

BRANCH_HEAD_SQL = """
SELECT w.detail, COALESCE(c.title, '') AS collaboration
FROM work_log w
LEFT JOIN collaboration c ON c.hashfname = w.hashfname
WHERE w.indx = :indx
"""

# 펼치기도 상한이 있으므로 전체 개수를 따로 센다.
# 300개만 보여주면서 그 사실을 안 알리면, 1,234개짜리 가지가 300개인 줄 알게 된다.
BRANCH_COUNT_SQL = """
SELECT COUNT(*) AS n
FROM work_log w
WHERE w.hashfname = (SELECT hashfname FROM work_log WHERE indx = :indx)
  AND w.detail IS (SELECT detail FROM work_log WHERE indx = :indx)
"""


def search(keyword: str, limit: int, filters: Filters) -> dict[str, Any]:
    limit = max(1, min(limit, MAX_LIMIT))
    where, filter_params = filters.where()
    params: dict[str, Any] = {
        "pattern": f"%{escape_like_literal(keyword)}%",
        "limit": limit,
        **filter_params,
    }

    conn = connect(read_only=True)
    try:
        # 임시 테이블에는 검색어에 걸리는 것을 전부 담는다(필터는 안 건다).
        # 필터는 아래에서 걸어야 패싯마다 자기 필터만 빼고 셀 수 있다.
        conn.execute("CREATE TEMP TABLE hit AS " + BUILD_HITS_SQL, {"pattern": params["pattern"]})

        results = [
            {
                "detail": r["detail"] or "",
                "collaboration": r["collaboration"],
                "last_author": r["last_author"],
                "last_at": r["last_at"] or "",
                "first_at": r["first_at"] or "",
                "event_count": r["event_count"],
                "kinds": (r["kinds"] or "").split(","),
                "is_deleted": r["last_gubun"] == "DEL",
                "branch_id": r["last_indx"],
            }
            for r in conn.execute(
                f"SELECT * FROM hit WHERE {where} ORDER BY last_indx DESC LIMIT :limit",
                params,
            )
        ]

        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM hit WHERE {where}", params
        ).fetchone()["n"]

        facets: dict[str, list[dict[str, Any]]] = {}
        for kind, column in (("year", "last_year"),
                             ("map", "collaboration"),
                             ("author", "last_author")):
            # 자기 자신은 빼고 센다(위 Filters.where 주석 참고).
            facet_where, facet_params = filters.where(exclude=kind)
            facets[kind] = [
                {"key": r["key"] or "", "count": r["n"]}
                for r in conn.execute(
                    f"SELECT {column} AS key, COUNT(*) AS n FROM hit "
                    f"WHERE {facet_where} GROUP BY 1",
                    {**facet_params, "pattern": params["pattern"]},
                )
            ]

        for kind in facets:
            facets[kind].sort(key=lambda item: (-item["count"], item["key"]))
        facets["year"].sort(key=lambda item: item["key"], reverse=True)
        # 상위 N개로 자르지 않는다. 종류가 41(작성자)·168(맵)로 묶여 있어 드롭다운이
        # 감당하고, 자르면 고를 수 없게 된 값이 몇 개인지도 알려주지 않는 조용한 절단이 된다.

        return {
            "count": len(results),
            "total": total,
            "limit": limit,
            "has_more": total > len(results),
            "facets": facets,
            "results": results,
            "sync": sync_status(conn),
        }
    finally:
        conn.close()


def expand(branch_id: int, limit: int = 300) -> dict[str, Any]:
    conn = connect(read_only=True)
    try:
        head = conn.execute(BRANCH_HEAD_SQL, {"indx": branch_id}).fetchone()
        if head is None:
            return {}
        events = [
            {
                "event_time": r["c_date"],
                "author": r["u_name"],
                "action_type": r["gubun"],
                # 이동 때문에 따라 찍힌 DEL은 '삭제'가 아니라고 화면에서도 구분한다.
                "move_pair": bool(r["move_pair"]),
            }
            for r in conn.execute(EXPAND_SQL, {"indx": branch_id, "limit": limit})
        ]
        total = conn.execute(BRANCH_COUNT_SQL, {"indx": branch_id}).fetchone()["n"]
        return {
            "detail": head["detail"] or "",
            "collaboration": head["collaboration"],
            "count": len(events),
            "total": total,
            "has_more": total > len(events),
            "events": events,
        }
    finally:
        conn.close()


def sync_status(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """색인이 얼마나 낡았는지. 동기화가 조용히 죽어도 검색은 계속 되기 때문에,
    화면이 이 값을 보여주지 않으면 낡은 결과를 최신인 줄 알고 보게 된다."""

    own = conn is None
    conn = conn or connect(read_only=True)
    try:
        last = get_state(conn, "last_sync_at")
        error = get_state(conn, "last_error")
        rows = get_state(conn, "row_count", "0")
        age_minutes: int | None = None
        if last:
            try:
                age_minutes = int(
                    (datetime.now().astimezone() - datetime.fromisoformat(last)).total_seconds() // 60
                )
            except ValueError:
                age_minutes = None
        return {
            "last_sync_at": last,
            "age_minutes": age_minutes,
            "row_count": int(rows or 0),
            "error": error,
        }
    finally:
        if own:
            conn.close()
