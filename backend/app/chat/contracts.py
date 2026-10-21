from dataclasses import dataclass, field

from pydantic import BaseModel

from app.providers.base import ProviderError
from app.schemas.chat import ChatTurnResponse


@dataclass(frozen=True)
class ProviderSnapshot:
    id: str
    user_id: str
    provider_type: str
    base_url: str
    chat_model: str
    embedding_model: str | None
    encrypted_api_key: str = field(repr=False)
    timeout_seconds: int
    tested: bool
    capabilities: dict
    fingerprint: str


@dataclass(frozen=True)
class PreparedTurn:
    turn_id: str
    space_id: str
    user_id: str
    session_hash: str = field(repr=False)
    lease_token: str
    intent_version: int
    concept_fingerprint: str
    provider_snapshot: ProviderSnapshot = field(repr=False)
    task: dict


@dataclass(frozen=True)
class ModelCallResult:
    validated: BaseModel | None
    elapsed_ms: int
    usage: dict
    error: ProviderError | None = None


@dataclass(frozen=True)
class TurnResult:
    http_status: int
    response: ChatTurnResponse


@dataclass(frozen=True)
class ApplicationResult:
    outcome: str
    changes: list[dict]
    before: dict
    after: dict
    revision_id: str | None
    plan: dict
