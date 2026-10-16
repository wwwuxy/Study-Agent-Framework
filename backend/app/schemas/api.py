from datetime import date
from typing import Literal

from pydantic import Field, SecretStr

from app.schemas.domain import StrictModel


class Credentials(StrictModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    password: SecretStr = Field(min_length=10, max_length=128)


class ProviderCreate(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    provider_type: Literal["openai_compatible", "openai_files", "fake", "fake_files"] = "openai_compatible"
    base_url: str = Field(default="https://api.openai.com/v1", max_length=2048)
    chat_model: str = Field(min_length=1, max_length=200)
    embedding_model: str | None = Field(default=None, min_length=1, max_length=200)
    api_key: SecretStr = Field(min_length=1, max_length=4096)
    timeout_seconds: int = Field(default=30, ge=5, le=60)


class ProviderUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    base_url: str | None = Field(default=None, min_length=1, max_length=2048)
    chat_model: str | None = Field(default=None, min_length=1, max_length=200)
    embedding_model: str | None = Field(default=None, min_length=1, max_length=200)
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=4096)
    timeout_seconds: int | None = Field(default=None, ge=5, le=60)


class IdempotentRequest(StrictModel):
    idempotency_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_\-]+$")


class SpaceCreate(IdempotentRequest):
    provider_id: str = Field(min_length=1, max_length=36)
    goal: str = Field(min_length=2, max_length=2000)
    daily_minutes: int = Field(default=30, ge=5, le=480)
    target_date: date | None = None
    expected_level: str = Field(default="基础掌握", min_length=1, max_length=200)


class SpaceUpdate(StrictModel):
    provider_id: str | None = None
    allow_general_knowledge: bool | None = None


class AttemptSubmit(IdempotentRequest):
    item_id: str = Field(min_length=1, max_length=36)
    answer: str = Field(min_length=1, max_length=12000)
    assistance_level: Literal["none", "hint", "solution"] = "none"
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)
