from __future__ import annotations

import io as _io
import logging
import re
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app import main
from app.sync import BOARD_SQL, FETCH_SQL


client = TestClient(main.app, raise_server_exceptions=False)


def test_index_is_served() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "씽크와이즈 위키" in response.text
    assert response.headers["cache-control"] == "no-store"


def test_search_rejects_trimmed_one_character_query() -> None:
    response = client.get("/api/search", params={"q": " 가 "})

    assert response.status_code == 422
    assert "2글자" in response.json()["detail"]


def test_search_rejects_limit_over_maximum() -> None:
    response = client.get("/api/search", params={"q": "클로드", "limit": 501})

    assert response.status_code == 422


def test_search_returns_folded_rows(index_db) -> None:
    response = client.get("/api/search", params={"q": "배관", "limit": 50})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "배관"
    assert payload["total"] == 1
    assert payload["has_more"] is False
    assert payload["results"][0]["event_count"] == 2
    assert payload["results"][0]["last_author"] == "김상훈"


def test_search_reports_truncation(index_db) -> None:
    """잘렸으면 잘렸다고 알려야 한다. 숫자만 조용히 모자라면 이게 전부인 줄 안다."""

    response = client.get("/api/search", params={"q": "가지", "limit": 1})

    payload = response.json()
    assert payload["total"] == 2
    assert payload["count"] == 1
    assert payload["has_more"] is True


def test_branch_expands(index_db) -> None:
    branch_id = client.get(
        "/api/search", params={"q": "배관"}
    ).json()["results"][0]["branch_id"]

    response = client.get(f"/api/branch/{branch_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert payload["total"] == 2
    assert payload["has_more"] is False


def test_branch_not_found(index_db) -> None:
    assert client.get("/api/branch/999999").status_code == 404


def test_deleted_branch_returns_the_same_404_as_a_missing_one(index_db) -> None:
    """삭제된 가지와 없는 가지가 구분되면 '지웠다'는 사실이 새어 나간다."""

    deleted = client.get("/api/branch/6")
    missing = client.get("/api/branch/999999")

    assert deleted.status_code == 404
    assert deleted.json()["detail"] == missing.json()["detail"]


def test_status_exposes_index_freshness(index_db) -> None:
    response = client.get("/api/status")

    assert response.status_code == 200
    assert response.json()["row_count"] == 7


def test_missing_index_is_reported_not_silently_empty(tmp_path, monkeypatch) -> None:
    """색인이 없을 때 '결과 0건'으로 보이면, 아직 준비가 안 된 것과
    정말 없는 것을 구분할 수 없다."""

    monkeypatch.setenv("INDEX_DB_PATH", str(tmp_path / "없는파일.db"))

    response = client.get("/api/search", params={"q": "배관"})

    assert response.status_code == 503
    assert "색인" in response.json()["detail"]


def test_sync_reads_production_with_select_only() -> None:
    """운영 DB에 나가는 문장은 읽기뿐이어야 한다."""

    for sql in (FETCH_SQL, BOARD_SQL):
        normalized = sql.lstrip().upper()
        assert normalized.startswith("SELECT")
        for forbidden in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "CREATE "):
            assert forbidden not in normalized


@pytest.fixture()
def access_log() -> Iterator[_io.StringIO]:
    """액세스 로그가 실제로 찍는 줄을 붙잡는다.

    이 로거는 propagate=False라 pytest의 caplog(root에 붙는다)로는 안 잡히고,
    핸들러가 import 시점의 sys.stdout을 이미 붙들고 있어 capsys로도 안 잡힌다.
    포맷터는 운영과 같은 것을 그대로 빌려 쓴다. 새로 만들면 시각 형식이 실제와
    달라져도 테스트는 통과해 버린다.
    """

    stream = _io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(main.access_logger.handlers[0].formatter)
    main.access_logger.addHandler(handler)
    try:
        yield stream
    finally:
        main.access_logger.removeHandler(handler)


def test_access_log_shows_time_and_readable_query(index_db, access_log) -> None:
    """uvicorn 기본 로그에는 시각이 없고 검색어가 %인코딩이라 사용 기록으로 못 썼다."""

    client.get("/api/search", params={"q": "배관", "limit": 50})

    line = access_log.getvalue().strip()
    assert re.match(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] ", line)
    assert "GET /api/search?q=배관&limit=50" in line
    assert " 200 " in line
    assert line.endswith("ms")


def test_access_log_records_failed_requests_too(access_log) -> None:
    """실패한 요청이 로그에서 빠지면 '아무도 안 썼다'와 구분이 안 된다."""

    client.get("/api/search", params={"q": "가"})

    assert " 422 " in access_log.getvalue()


def test_access_log_cannot_be_forged_with_a_newline(index_db, access_log) -> None:
    """검색어는 사용자가 보낸 값이다. 줄바꿈을 그대로 풀어 쓰면 로그에 가짜 줄을
    끼워 넣을 수 있고, 그러면 로그를 근거로 쓸 수 없게 된다."""

    forged = "배관" + chr(10) + "[2026-01-01 00:00:00] 가짜 줄"

    client.get("/api/search", params={"q": forged})

    assert len(access_log.getvalue().strip().splitlines()) == 1
