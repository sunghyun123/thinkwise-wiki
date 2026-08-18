"""테스트용 색인을 만든다. 운영 MariaDB에는 접속하지 않는다.

실제 데이터에서 발견된 까다로운 경우를 그대로 넣어 둔다.
  - 이동(MOVE) 때문에 따라 찍힌 DEL      : 삭제로 보면 안 된다(실데이터의 MOVE 88%)
  - 진짜로 지워진 가지                    : 삭제로 보여야 한다
  - 작성자가 빈 채로 남은 마지막 기록     : 이름이 통째로 사라지면 안 된다(실데이터의 12.1%)
  - 협업명을 못 찾는 가지                 : 빈칸이어야 한다(실데이터의 32.7%)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


ROWS = [
    # indx, c_date,                u_name,   gubun,  detail,             hashfname
    (1, "2021-01-04 09:00:00", "김상훈", "ADD",   "배관 공사 검토",   "AAA"),
    (2, "2021-02-08 11:30:00", "",       "EDIT",  "배관 공사 검토",   "AAA"),
    (3, "2022-03-02 14:00:00", "김무선", "MOVE",  "옮겨진 가지",      "AAA"),
    (4, "2022-03-02 14:00:00", "김무선", "DEL",   "옮겨진 가지",      "AAA"),
    (5, "2023-01-09 10:00:00", "조성현", "ADD",   "지워진 가지",      "BBB"),
    (6, "2023-05-11 16:20:00", "조성현", "DEL",   "지워진 가지",      "BBB"),
]

# AAA에는 맵 이름이 있고 BBB는 없다.
COLLABORATIONS = [("AAA", "영진 프로젝트")]


@pytest.fixture()
def index_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "test_index.db"
    monkeypatch.setenv("INDEX_DB_PATH", str(db_path))

    from app.index_db import SCHEMA
    from app.sync import MARK_MOVE_PAIR_SQL

    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.executemany(
        "INSERT INTO work_log(indx, c_date, u_name, gubun, detail, hashfname)"
        " VALUES(?, ?, ?, ?, ?, ?)",
        ROWS,
    )
    conn.executemany(
        "INSERT INTO collaboration(hashfname, title) VALUES(?, ?)", COLLABORATIONS
    )
    # 표시 규칙을 테스트가 따로 흉내 내지 않도록, 운영과 같은 SQL로 표시한다.
    conn.execute(MARK_MOVE_PAIR_SQL, (0,))
    conn.executemany(
        "INSERT INTO sync_state(key, value) VALUES(?, ?)",
        [("last_indx", "6"), ("row_count", str(len(ROWS))), ("last_error", "")],
    )
    conn.commit()
    conn.close()
    return db_path
