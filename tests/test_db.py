from app.db import SEARCH_SQL, escape_like_literal


def test_application_business_sql_is_read_only_select() -> None:
    normalized = SEARCH_SQL.lstrip().upper()

    assert normalized.startswith("SELECT")
    assert "INSERT " not in normalized
    assert "UPDATE " not in normalized
    assert "DELETE " not in normalized
    assert "DROP " not in normalized
    assert "ALTER " not in normalized
    assert "ORDER BY W.C_DATE DESC" in normalized
    assert "LIMIT %S" in normalized


def test_like_wildcards_are_treated_as_literal_characters() -> None:
    assert escape_like_literal("50%_완료!") == "50!%!_완료!!"

