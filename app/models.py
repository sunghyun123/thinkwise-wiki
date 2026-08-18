from pydantic import BaseModel, Field


class SearchItem(BaseModel):
    event_time: str = Field(description="작업 시각")
    author: str = Field(description="작성자")
    action_type: str = Field(description="작업 구분")
    detail: str = Field(description="가지 내용")
    collaboration: str = Field(description="협업명")


class SearchResponse(BaseModel):
    query: str
    count: int
    limit: int
    has_more: bool
    results: list[SearchItem]

