from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)


def test_index_is_served() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "씽크와이즈 위키" in response.text
    assert response.headers["cache-control"] == "no-store"


def test_search_rejects_trimmed_one_character_query() -> None:
    response = client.get("/api/search", params={"q": " 가 ", "limit": 50})

    assert response.status_code == 422
    assert "2글자" in response.json()["detail"]


def test_search_rejects_limit_over_100() -> None:
    response = client.get("/api/search", params={"q": "클로드", "limit": 101})

    assert response.status_code == 422


def test_search_returns_latest_rows(monkeypatch) -> None:
    expected = [
        {
            "event_time": "2026-08-14 17:31:21",
            "author": "조성현",
            "action_type": "ADD",
            "detail": "클로드 내의 조직 스킬을 활용",
            "collaboration": "조성현",
        }
    ]

    monkeypatch.setattr(main, "get_database_settings", lambda: object())
    monkeypatch.setattr(
        main, "search_work_logs", lambda settings, keyword, limit: (expected, False)
    )

    response = client.get("/api/search", params={"q": " 클로드 ", "limit": 20})

    assert response.status_code == 200
    assert response.json() == {
        "query": "클로드",
        "count": 1,
        "limit": 20,
        "has_more": False,
        "results": expected,
    }

