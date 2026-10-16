from typing import Literal

from pydantic import Field, model_validator

from app.schemas.domain import StrictModel


class Chapter(StrictModel):
    section_id: str = Field(min_length=1, max_length=80, pattern=r"^[\w-]+$")
    heading: str = Field(min_length=1, max_length=300)


class RemoteOutline(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    sections: list[Chapter] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def unique_sections(self):
        if len({s.section_id for s in self.sections}) != len(self.sections):
            raise ValueError("重复章节 ID")
        return self


class Locator(StrictModel):
    chapter: str | None = Field(default=None, max_length=300)
    page: int | None = Field(default=None, ge=1)


class RemoteSection(StrictModel):
    section_id: str = Field(min_length=1, max_length=80)
    heading: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=12000)
    keywords: list[str] = Field(min_length=1, max_length=30)
    concepts: list[str] = Field(min_length=1, max_length=30)
    locator: Locator = Field(default_factory=Locator)
    locator_verified: bool = False


class Rerank(StrictModel):
    source_ids: list[str] = Field(max_length=10)


class MaterialRetry(StrictModel):
    idempotency_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    consent: bool = False
    use_embeddings: bool = False


class MaterialSearch(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    mode: Literal["auto", "keyword", "embedding"] = "auto"
    limit: int = Field(default=5, ge=1, le=10)
