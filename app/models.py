from pydantic import BaseModel, Field


class FacetItem(BaseModel):
    key: str = Field(description="필터 값(연도·맵 이름·작성자)")
    count: int = Field(description="이 값에 해당하는 가지 수")


class Facets(BaseModel):
    year: list[FacetItem] = []
    map: list[FacetItem] = []
    author: list[FacetItem] = []


class SyncStatus(BaseModel):
    last_sync_at: str = Field(default="", description="색인을 마지막으로 갱신한 시각")
    age_minutes: int | None = Field(default=None, description="갱신 후 지난 시간(분)")
    row_count: int = Field(default=0, description="색인이 담고 있는 원본 행 수")
    error: str = Field(default="", description="마지막 동기화 실패 내용")


class SearchItem(BaseModel):
    """가지 하나. 같은 협업 안의 같은 내용은 한 줄로 접혀 있다."""

    detail: str = Field(description="가지 내용")
    collaboration: str = Field(description="맵 이름")
    last_author: str = Field(description="마지막으로 수정한 사람(이름이 남은 가장 최근)")
    last_at: str = Field(description="마지막 수정 시각")
    first_at: str = Field(description="처음 만들어진 시각")
    event_count: int = Field(description="이 가지에 남은 작업 기록 수")
    kinds: list[str] = Field(description="어떤 종류의 작업이 있었나")
    is_deleted: bool = Field(description="현재 삭제된 상태인가")
    branch_id: int = Field(description="펼치기에 쓰는 식별자")


class SearchResponse(BaseModel):
    query: str
    count: int = Field(description="이번 응답에 담긴 가지 수")
    total: int = Field(description="조건에 맞는 전체 가지 수")
    limit: int
    has_more: bool
    facets: Facets
    sync: SyncStatus
    results: list[SearchItem]


class BranchEvent(BaseModel):
    event_time: str
    author: str
    action_type: str
    move_pair: bool = Field(
        description="가지를 옮기느라 따라 찍힌 기록인가(진짜 삭제가 아님)"
    )


class BranchResponse(BaseModel):
    detail: str
    collaboration: str
    count: int = Field(description="이번 응답에 담긴 기록 수")
    total: int = Field(description="이 가지에 남은 전체 기록 수")
    has_more: bool = Field(description="상한에 걸려 잘렸는가")
    events: list[BranchEvent]
