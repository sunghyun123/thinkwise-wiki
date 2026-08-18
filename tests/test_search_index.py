"""접기·삭제 판정·작성자 보정이 실제 데이터의 함정을 견디는지 본다."""

from __future__ import annotations

from app.search_index import Filters, expand, search


def _by_detail(results: list[dict], text: str) -> dict:
    return next(item for item in results if item["detail"] == text)


def test_repeated_events_fold_into_one_row(index_db) -> None:
    payload = search("배관", 50, Filters())

    assert payload["total"] == 1
    branch = payload["results"][0]
    assert branch["event_count"] == 2          # ADD + EDIT 두 기록이 한 줄로
    assert branch["first_at"].startswith("2021-01-04")
    assert branch["last_at"].startswith("2021-02-08")
    assert sorted(branch["kinds"]) == ["ADD", "EDIT"]


def test_author_falls_back_to_last_named_event(index_db) -> None:
    """마지막 기록(EDIT)의 작성자가 비어 있어도 이름이 사라지면 안 된다."""

    branch = search("배관", 50, Filters())["results"][0]

    assert branch["last_author"] == "김상훈"


def test_move_pair_is_not_treated_as_deletion(index_db) -> None:
    """가지를 옮기면 MOVE 뒤에 DEL이 따라 찍힌다. 이걸 삭제로 보면
    실데이터에서 멀쩡한 가지 18,197개에 '삭제됨'이 붙는다."""

    moved = _by_detail(search("가지", 50, Filters())["results"], "옮겨진 가지")

    assert moved["is_deleted"] is False


def test_real_deletion_is_reported(index_db) -> None:
    deleted = _by_detail(search("가지", 50, Filters())["results"], "지워진 가지")

    assert deleted["is_deleted"] is True


def test_missing_collaboration_stays_blank(index_db) -> None:
    deleted = _by_detail(search("가지", 50, Filters())["results"], "지워진 가지")
    moved = _by_detail(search("가지", 50, Filters())["results"], "옮겨진 가지")

    assert deleted["collaboration"] == ""
    assert moved["collaboration"] == "영진 프로젝트"


def test_facets_partition_the_result_set(index_db) -> None:
    payload = search("가지", 50, Filters())

    assert sum(item["count"] for item in payload["facets"]["year"]) == payload["total"]


def test_facet_options_do_not_collapse_to_the_current_filter(index_db) -> None:
    """연도를 고른 뒤에도 다른 연도가 선택지에 남아야 한다.
    남지 않으면 드롭다운이 '연도를 바꾸는 도구'로서 죽는다."""

    payload = search("가지", 50, Filters(year="2022"))

    assert payload["total"] == 1
    assert {item["key"] for item in payload["facets"]["year"]} == {"2022", "2023"}


def test_filters_narrow_the_result(index_db) -> None:
    payload = search("가지", 50, Filters(year="2023"))

    assert payload["total"] == 1
    assert payload["results"][0]["detail"] == "지워진 가지"


def test_like_wildcards_are_treated_as_literal_characters(index_db) -> None:
    from app.search_index import escape_like_literal

    assert escape_like_literal("50%_완료!") == "50!%!_완료!!"
    # 와일드카드가 살아 있었다면 '%'가 전부와 일치해 결과가 나왔을 것이다.
    assert search("%가지", 50, Filters())["total"] == 0


def test_expand_returns_original_events(index_db) -> None:
    branch = search("배관", 50, Filters())["results"][0]

    detail = expand(branch["branch_id"])

    assert detail["count"] == 2
    assert [event["action_type"] for event in detail["events"]] == ["EDIT", "ADD"]


def test_expand_reports_its_own_cap(index_db) -> None:
    """펼치기에도 상한이 있다. 잘렸다는 사실을 안 알리면
    1,234개짜리 가지가 300개인 줄 알게 된다."""

    branch = search("배관", 50, Filters())["results"][0]

    capped = expand(branch["branch_id"], limit=1)

    assert capped["count"] == 1
    assert capped["total"] == 2
    assert capped["has_more"] is True


def test_expand_marks_move_pair_events(index_db) -> None:
    moved = _by_detail(search("가지", 50, Filters())["results"], "옮겨진 가지")

    events = expand(moved["branch_id"])["events"]

    assert [event["move_pair"] for event in events] == [True, False]
