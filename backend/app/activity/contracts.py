from dataclasses import dataclass, field
from datetime import date, datetime

from app.chat.contracts import ProviderSnapshot
from app.learner.parameters import BKTParameters


@dataclass(frozen=True)
class CalendarPeriod:
    key: str
    timezone: str
    start: datetime
    end: datetime
    warning: str | None = None


@dataclass(frozen=True)
class JobClaim:
    job_id: str
    token: str
    user_id: str
    space_id: str
    kind: str
    period_key: str
    generation: int


@dataclass(frozen=True)
class ActivitySnapshot:
    user_id: str
    space_id: str
    now: datetime
    intent: dict
    concepts: tuple[dict, ...]
    states: dict
    memory: dict
    events: tuple[dict, ...]
    active_lesson: dict | None
    tasks: tuple[dict, ...]
    fingerprint: str
    bkt_parameters: BKTParameters = field(default_factory=BKTParameters)


@dataclass(frozen=True)
class PreparedAnalysis:
    run_id: str
    user_id: str
    space_id: str
    session_hash: str = field(repr=False)
    lease_token: str
    source_fingerprint: str
    provider_snapshot: ProviderSnapshot = field(repr=False)
    payload: dict
    reserved_tokens: int
    budget_date: date
