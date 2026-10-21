from pydantic import Field

from app.schemas.api import IdempotentRequest


class ReviewStart(IdempotentRequest):
    concept_id: str = Field(min_length=1, max_length=80)
