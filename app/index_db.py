"""로컬 검색 색인(SQLite)의 스키마와 연결을 담당한다.

운영 MariaDB를 매 검색마다 훑는 대신, work_log를 이 파일 하나로 복제해 두고
검색은 여기서만 한다. 실측 근거는 docs/deploy-log.md에 남긴다.
  - 운영 MariaDB에서 `LIKE '%공사%'` 1회 = 53만행 풀스캔 663ms
  - 같은 검색을 로컬 SQLite에서 = 25ms, 정렬+LIMIT까지 붙여도 1ms 미만

설계에서 지킨 두 가지 원칙:
  1. 여기에는 원본 이벤트를 그대로 담는다. 접기(같은 가지의 반복 이벤트 합치기)는
     저장하지 않고 검색할 때 GROUP BY로 파생시킨다. 접힌 요약을 저장하면 새 이벤트가
     들어올 때마다 갱신해야 하고, 갱신 경로를 하나라도 빠뜨리면 영구히 어긋난다.
  2. 협업명(TITLE)도 각 행에 박아두지 않는다. 87행짜리 표를 따로 두고 검색할 때
     조인한다. 같은 이유(파생값을 저장하지 않는다)이고, 87행 조인은 사실상 공짜다.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .config import PROJECT_ROOT


def get_index_db_path() -> Path:
    """색인 파일 위치. 서버/개인 PC에서 각각 다른 곳을 쓸 수 있게 env로 열어둔다."""

    override = os.getenv("INDEX_DB_PATH", "").strip()
    if override:
        return Path(override)
    return PROJECT_ROOT / "data" / "wiki_index.db"


SCHEMA = """
-- 운영 tw_colla_log.work_log의 사본. 가공하지 않는다.
CREATE TABLE IF NOT EXISTS work_log (
    indx      INTEGER PRIMARY KEY,   -- 운영 PK 그대로. 증분 커서이자 정렬 키
    c_date    TEXT NOT NULL,
    u_name    TEXT NOT NULL DEFAULT '',
    gubun     TEXT NOT NULL DEFAULT '',
    detail    TEXT,
    hashfname TEXT NOT NULL DEFAULT '',
    -- 이동(MOVE) 때문에 따라 찍힌 DEL인가. 삭제 판정에서 제외하려고 표시해 둔다.
    -- 이건 파생값이지만 과거 행은 다시 바뀌지 않는 '불변' 파생이라 저장해도 안전하다.
    move_pair INTEGER NOT NULL DEFAULT 0
);

-- 접기(같은 협업 + 같은 내용)를 검색 시점에 하므로 그 조합에 인덱스를 준다.
CREATE INDEX IF NOT EXISTS ix_work_log_fold ON work_log(hashfname, detail);

-- 협업명. 운영에서 통째로 다시 받아 덮어쓰므로 낡을 창이 없다(87행).
CREATE TABLE IF NOT EXISTS collaboration (
    hashfname TEXT PRIMARY KEY,
    title     TEXT NOT NULL DEFAULT ''
);

-- 어디까지 가져왔는지, 마지막 동기화가 언제 성공/실패했는지.
-- 화면에 "마지막 갱신 N분 전"을 띄우려면 이 값이 필요하다. 동기화가 조용히 죽어도
-- 검색은 계속 되기 때문에, 알려주지 않으면 낡은 결과를 최신인 줄 알고 보게 된다.
CREATE TABLE IF NOT EXISTS sync_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class IndexUnavailableError(RuntimeError):
    """색인 파일이 아직 없거나 비어 있을 때. 동기화를 먼저 돌려야 한다."""


def connect(path: Path | None = None, *, read_only: bool = False) -> sqlite3.Connection:
    """색인 파일에 연결한다.

    WAL 모드를 쓰는 이유: 동기화가 쓰는 동안에도 웹 서버가 막히지 않고 읽어야 한다.
    기본 모드에서는 쓰는 쪽이 파일 전체를 잠가서 검색이 그동안 멈춘다.
    """

    db_path = path or get_index_db_path()

    if read_only:
        # 색인이 없는데 조용히 빈 파일을 만들면 "검색 결과 0건"으로 보인다.
        # 아직 동기화를 안 돌린 것과 정말 결과가 없는 것은 다른 상황이므로 구분해 알린다.
        if not db_path.exists():
            raise IndexUnavailableError(
                f"검색 색인이 없습니다({db_path}). "
                "`python -m app.sync --full`을 먼저 실행해 주세요."
            )
        return _with_row_factory(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True))

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)

    conn.execute("PRAGMA journal_mode=WAL")
    # 색인은 언제든 운영 DB에서 다시 만들 수 있으므로 내구성보다 속도를 택한다.
    conn.execute("PRAGMA synchronous=NORMAL")
    return _with_row_factory(conn)


def _with_row_factory(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def get_state(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO sync_state(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
