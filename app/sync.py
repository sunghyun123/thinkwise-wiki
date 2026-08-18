"""운영 MariaDB의 work_log를 로컬 색인으로 증분 복제한다.

    python -m app.sync           # 새로 생긴 것만 가져온다 (평소)
    python -m app.sync --full    # 처음부터 다시 만든다

증분의 근거: work_log.indx는 PK(auto_increment)이고, 실측 결과 indx 순서와 c_date
순서가 완전히 일치한다(역전 0건 / 53만행). 그래서 "마지막으로 가져온 indx보다 큰 것"만
읽으면 되고, 이 조건은 PK 인덱스 범위 스캔이라 운영 DB에 거의 부담을 주지 않는다.
지금 앱이 검색 1회에 일으키는 풀스캔보다 훨씬 가볍다.

전제(확인하지 않은 가정): 운영에서 과거 행을 수정하거나 삭제하지 않는다.
감사 로그라 그럴 일이 없어 보이지만 검증한 사실은 아니다. 만약 과거가 바뀐다면
indx 커서 방식은 그걸 못 따라가므로 --full로 다시 만들어야 한다.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from .config import ConfigurationError, get_database_settings
from .index_db import connect, ensure_schema, get_state, set_state


# 한 번에 가져오는 행 수. 운영 DB를 오래 붙잡지 않으면서 왕복도 줄이는 절충점이다.
BATCH_SIZE = 5000

FETCH_SQL = """
SELECT indx, c_date, u_name, gubun, detail, hashfname
FROM tw_colla_log.work_log
WHERE indx > %s
ORDER BY indx
LIMIT %s
"""

BOARD_SQL = "SELECT HASHFNAME, TITLE FROM tw_colman.collaboration_board"

# MOVE 바로 뒤(indx+1)에 같은 내용·같은 시각으로 찍힌 DEL을 표시한다.
# 씽크와이즈는 가지를 옮길 때 MOVE와 DEL을 쌍으로 남긴다(실측: MOVE의 88%).
# 표시해 두지 않으면 "마지막 이벤트가 DEL이니 삭제됨"으로 판정해서
# 멀쩡히 살아 있는 가지 3만 개에 '삭제됨'이 붙는다.
MARK_MOVE_PAIR_SQL = """
UPDATE work_log
SET move_pair = 1
WHERE indx > ?
  AND gubun = 'DEL'
  AND EXISTS (
      SELECT 1 FROM work_log AS m
      WHERE m.indx = work_log.indx - 1
        AND m.gubun = 'MOVE'
        AND m.c_date = work_log.c_date
        AND m.detail IS work_log.detail
  )
"""


def _log(message: str) -> None:
    # 작업 스케줄러로 돌면 콘솔이 없다. 시각을 붙여 로그 파일에서 읽을 수 있게 한다.
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def _open_source() -> pymysql.connections.Connection:
    settings = get_database_settings()
    return pymysql.connect(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password,
        charset="utf8mb4",
        # 한 번에 BATCH_SIZE 행만 받으므로 기본 커서로 충분하다.
        cursorclass=DictCursor,
        connect_timeout=settings.connect_timeout,
        read_timeout=60,
        autocommit=True,
    )


def _sync_collaborations(source: Any, conn: sqlite3.Connection) -> int:
    """협업명 표(87행)를 통째로 새로 받아 덮어쓴다.

    증분이 아니라 전량 교체인 이유: 87행뿐이라 비용이 없고, 제목이 바뀌거나
    협업이 지워진 경우까지 별도 로직 없이 따라간다.
    """

    with source.cursor() as cur:
        cur.execute(BOARD_SQL)
        rows = [(r["HASHFNAME"], r["TITLE"] or "") for r in cur.fetchall()]

    conn.execute("DELETE FROM collaboration")
    conn.executemany(
        "INSERT INTO collaboration(hashfname, title) VALUES(?, ?)", rows
    )
    return len(rows)


def _sync_work_log(
    source: Any, conn: sqlite3.Connection, cursor_indx: int, commit_each: bool = True
) -> tuple[int, int]:
    """indx 커서 이후의 행을 배치로 가져온다. (가져온 행 수, 새 커서)를 돌려준다.

    commit_each=False면 전부 한 트랜잭션으로 묶는다. 전체 재적재(--full)에서 쓴다.
    배치마다 커밋하면 비우고 다시 채우는 20초 동안 검색하는 사람이 '아직 덜 채워진 색인'을
    보게 되고, 그건 결과가 조용히 모자란 것과 같다. 한 묶음으로 하면 커밋되기 전까지
    읽는 쪽은 예전 색인을 그대로 본다.
    """

    fetched = 0
    while True:
        with source.cursor() as cur:
            cur.execute(FETCH_SQL, (cursor_indx, BATCH_SIZE))
            rows = cur.fetchall()

        if not rows:
            break

        payload = [
            (
                r["indx"],
                r["c_date"].isoformat(sep=" ", timespec="seconds")
                if hasattr(r["c_date"], "isoformat")
                else str(r["c_date"]),
                r["u_name"] or "",
                r["gubun"] or "",
                r["detail"],
                r["hashfname"] or "",
            )
            for r in rows
        ]

        # OR REPLACE: 같은 구간을 두 번 돌려도 결과가 같다(멱등).
        # 중간에 끊겨도 커서만 되돌리고 다시 돌리면 되게 만드는 안전장치다.
        conn.executemany(
            "INSERT OR REPLACE INTO work_log"
            "(indx, c_date, u_name, gubun, detail, hashfname)"
            " VALUES(?, ?, ?, ?, ?, ?)",
            payload,
        )

        batch_start = cursor_indx
        cursor_indx = int(rows[-1]["indx"])
        fetched += len(rows)

        # 이번에 들어온 구간에 대해서만 MOVE/DEL 쌍을 표시한다.
        # 짝이 되는 MOVE(indx-1)는 오름차순으로 넣으므로 이미 들어와 있다.
        conn.execute(MARK_MOVE_PAIR_SQL, (batch_start,))

        set_state(conn, "last_indx", str(cursor_indx))
        if commit_each:
            # 증분일 때는 배치마다 커밋해 둔다. 중간에 끊겨도 거기까지는 살아남는다.
            conn.commit()
        _log(f"  {fetched:,}행 (indx {cursor_indx:,}까지)")

        if len(rows) < BATCH_SIZE:
            break

    return fetched, cursor_indx


def run(full: bool = False) -> int:
    conn = connect()
    ensure_schema(conn)

    cursor_indx = int(get_state(conn, "last_indx", "0") or 0)

    if full:
        # 비우기와 다시 채우기를 한 트랜잭션에 묶는다. 커밋 전까지 검색하는 쪽은
        # 예전 색인을 그대로 보므로, 재적재 중에 결과가 비거나 모자라는 일이 없다.
        _log("--full: 기존 색인을 비우고 처음부터 다시 만든다(한 트랜잭션)")
        conn.execute("DELETE FROM work_log")
        cursor_indx = 0

    _log(f"동기화 시작 (마지막 indx {cursor_indx:,})")

    source = _open_source()
    try:
        boards = _sync_collaborations(source, conn)
        fetched, cursor_indx = _sync_work_log(
            source, conn, cursor_indx, commit_each=not full
        )
    finally:
        source.close()

    total = conn.execute("SELECT COUNT(*) AS n FROM work_log").fetchone()["n"]
    # 오프셋을 붙여 저장한다. 나중에 다른 시간대에서 이 값을 읽어도 해석이 갈리지 않는다.
    set_state(conn, "last_sync_at", datetime.now().astimezone().isoformat(timespec="seconds"))
    set_state(conn, "last_error", "")
    set_state(conn, "row_count", str(total))
    conn.commit()
    conn.close()

    _log(f"완료: 새로 {fetched:,}행, 협업명 {boards}개, 색인 총 {total:,}행")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="씽크와이즈 위키 검색 색인 동기화")
    parser.add_argument("--full", action="store_true",
                        help="증분이 아니라 처음부터 다시 만든다")
    args = parser.parse_args()

    try:
        return run(full=args.full)
    except ConfigurationError as exc:
        _log(f"설정 오류: {exc}")
        return 2
    except pymysql.MySQLError as exc:
        # 운영 DB에 못 붙어도 색인은 그대로 남아 검색은 계속 된다.
        # 다만 결과가 낡으므로 실패 사실을 색인에 적어 화면이 알릴 수 있게 한다.
        _log(f"운영 DB 조회 실패: {exc}")
        _record_failure(f"DB 조회 실패: {exc}")
        return 3
    except Exception as exc:  # noqa: BLE001
        _log(f"예상하지 못한 실패: {exc!r}")
        _record_failure(f"{exc!r}")
        return 4


def _record_failure(message: str) -> None:
    """실패를 색인에 남긴다. 여기서 또 실패하면 원래 오류를 덮으므로 조용히 넘긴다."""

    try:
        conn = connect()
        ensure_schema(conn)
        set_state(conn, "last_error", message[:500])
        set_state(conn, "last_error_at",
                  datetime.now().astimezone().isoformat(timespec="seconds"))
        conn.commit()
        conn.close()
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    sys.exit(main())
