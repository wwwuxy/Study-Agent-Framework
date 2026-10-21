from typing import Annotated, Literal

from pydantic import Field

from app.schemas.api import IdempotentRequest
from app.schemas.domain import StrictModel


class AnalysisRequest(IdempotentRequest):
    source_kind: Literal["daily_plan", "weekly_summary"]
    source_id: str = Field(min_length=1, max_length=36)
    retry_of: str | None = Field(default=None, max_length=36)


class AnalysisContent(StrictModel):
    summary: str = Field(min_length=1, max_length=4000)
    recommendations: list[Annotated[str, Field(max_length=1000)]] = Field(default_factory=list, max_length=6)
    caveats: list[Annotated[str, Field(max_length=1000)]] = Field(default_factory=list, max_length=6)


class AnalysisResponse(StrictModel):
    id: str
    study_space_id: str
    idempotency_key: str
    source_kind: Literal["daily_plan", "weekly_summary"]
    source_id: str
    status: Literal["processing", "completed", "failed", "conflict", "cancelled"]
    content: AnalysisContent | None = None
    reserved_tokens: int
    actual_tokens: int | None = None
    usage_status: str
    retry_of: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    is_demo: bool = False
    retry_allowed: bool = False
    created_at: str


class AnalysisUsageResponse(StrictModel):
    utc_date: str
    calls: int
    call_limit: int
    occupied_tokens: int
    actual_tokens: int
    token_limit: int
    unknown_calls: int
    currency_cost: None = None
    notice: str
