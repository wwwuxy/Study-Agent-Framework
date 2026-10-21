import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    DDL,
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id():
    return str(uuid.uuid4())


def utcnow():
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProviderConfig(Base):
    __tablename__ = "provider_configs"
    __table_args__ = (UniqueConstraint("user_id", "id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    provider_type: Mapped[str] = mapped_column(String(40))
    base_url: Mapped[str] = mapped_column(Text)
    chat_model: Mapped[str] = mapped_column(String(200))
    embedding_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    encrypted_api_key: Mapped[str] = mapped_column(Text)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    tested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StudySpace(Base):
    __tablename__ = "study_spaces"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "init_key"),
        ForeignKeyConstraint(["user_id", "provider_id"], ["provider_configs.user_id", "provider_configs.id"]),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    provider_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    goal: Mapped[str] = mapped_column(Text)
    target_date: Mapped[str | None] = mapped_column(String(10))
    daily_minutes: Mapped[int] = mapped_column(Integer, default=30)
    expected_level: Mapped[str] = mapped_column(String(200), default="基础掌握")
    allow_general_knowledge: Mapped[bool] = mapped_column(Boolean, default=False)
    algorithm_versions: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {"bkt": "pybkt_v1", "fsrs": "fsrs_v6"},
        server_default='{"bkt":"pybkt_v1","fsrs":"fsrs_v6"}',
    )
    init_key: Mapped[str] = mapped_column(String(100))
    request_digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="ready")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeConcept(Base):
    __tablename__ = "knowledge_concepts"
    space_id: Mapped[str] = mapped_column(ForeignKey("study_spaces.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)


class ConceptPrerequisite(Base):
    __tablename__ = "concept_prerequisites"
    __table_args__ = (
        ForeignKeyConstraint(
            ["space_id", "concept_key"], ["knowledge_concepts.space_id", "knowledge_concepts.key"]
        ),
        ForeignKeyConstraint(
            ["space_id", "prerequisite_key"], ["knowledge_concepts.space_id", "knowledge_concepts.key"]
        ),
    )
    space_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    concept_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    prerequisite_key: Mapped[str] = mapped_column(String(80), primary_key=True)


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (
        UniqueConstraint("space_id", "init_key"),
        UniqueConstraint("space_id", "id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    space_id: Mapped[str] = mapped_column(ForeignKey("study_spaces.id"), index=True)
    init_key: Mapped[str] = mapped_column(String(100))
    action: Mapped[dict] = mapped_column(JSON)
    content: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AssessmentItem(Base):
    __tablename__ = "assessment_items"
    __table_args__ = (
        UniqueConstraint("space_id", "id"),
        UniqueConstraint("space_id", "prompt_hash"),
        ForeignKeyConstraint(["space_id", "lesson_id"], ["lessons.space_id", "lessons.id"]),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    space_id: Mapped[str] = mapped_column(ForeignKey("study_spaces.id"), index=True)
    lesson_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    purpose: Mapped[str] = mapped_column(String(30))
    prompt_hash: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON)


class AssessmentAttempt(Base):
    __tablename__ = "assessment_attempts"
    __table_args__ = (
        UniqueConstraint("space_id", "item_id"),
        UniqueConstraint("space_id", "idempotency_key"),
        ForeignKeyConstraint(["space_id", "item_id"], ["assessment_items.space_id", "assessment_items.id"]),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    space_id: Mapped[str] = mapped_column(ForeignKey("study_spaces.id"), index=True)
    item_id: Mapped[str] = mapped_column(String(36))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    request_digest: Mapped[str] = mapped_column(String(64))
    answer: Mapped[str] = mapped_column(Text)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LearningEvent(Base):
    __tablename__ = "learning_events"
    __table_args__ = (
        UniqueConstraint("space_id", "idempotency_key"),
        ForeignKeyConstraint(["user_id", "space_id"], ["study_spaces.user_id", "study_spaces.id"]),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    space_id: Mapped[str] = mapped_column(String(36), index=True)
    type: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    data: Mapped[dict] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LearnerConceptState(Base):
    __tablename__ = "learner_concept_states"
    __table_args__ = (
        ForeignKeyConstraint(
            ["space_id", "concept_id"], ["knowledge_concepts.space_id", "knowledge_concepts.key"]
        ),
    )
    space_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    concept_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)


class LearningPlan(Base):
    __tablename__ = "learning_plans"
    space_id: Mapped[str] = mapped_column(ForeignKey("study_spaces.id"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    space_id: Mapped[str | None] = mapped_column(ForeignKey("study_spaces.id"), nullable=True, index=True)
    provider_id: Mapped[str] = mapped_column(String(36))
    model: Mapped[str] = mapped_column(String(200))
    step: Mapped[str] = mapped_column(String(40))
    elapsed_ms: Mapped[int] = mapped_column(Integer)
    usage: Mapped[dict] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# Evidence is immutable while a space is retained. Explicit permanent deletion
# may erase events, but never update their historical contents.
for operation in ("UPDATE", "DELETE"):
    condition = (
        "WHEN NOT EXISTS (SELECT 1 FROM study_spaces WHERE id = OLD.space_id "
        "AND user_id = OLD.user_id AND status = 'deleted') "
        if operation == "DELETE"
        else ""
    )
    event.listen(
        LearningEvent.__table__,
        "after_create",
        DDL(
            f"CREATE TRIGGER learning_events_no_{operation.lower()} BEFORE {operation} ON learning_events "
            + condition
            + "BEGIN SELECT RAISE(ABORT, 'learning_events are append-only'); END"
        ).execute_if(dialect="sqlite"),
    )

event.listen(
    LearningEvent.__table__,
    "after_create",
    DDL("""
CREATE FUNCTION reject_learning_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
IF TG_OP = 'DELETE' AND EXISTS (
    SELECT 1 FROM study_spaces WHERE id = OLD.space_id AND user_id = OLD.user_id AND status = 'deleted'
) THEN RETURN OLD; END IF;
RAISE EXCEPTION 'learning_events are append-only'; END; $$
""").execute_if(dialect="postgresql"),
)
event.listen(
    LearningEvent.__table__,
    "after_create",
    DDL("""
CREATE TRIGGER learning_events_immutable BEFORE UPDATE OR DELETE ON learning_events
FOR EACH ROW EXECUTE FUNCTION reject_learning_event_mutation()
""").execute_if(dialect="postgresql"),
)


class MaterialAsset(Base):
    __tablename__ = "material_assets"
    __table_args__ = (
        UniqueConstraint("space_id", "upload_key"),
        UniqueConstraint("space_id", "id"),
        ForeignKeyConstraint(["user_id", "space_id"], ["study_spaces.user_id", "study_spaces.id"]),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    space_id: Mapped[str] = mapped_column(String(36), index=True)
    provider_id: Mapped[str] = mapped_column(String(36))
    provider_fingerprint: Mapped[str] = mapped_column(String(64))
    upload_key: Mapped[str] = mapped_column(String(100))
    request_digest: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(200))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    generation: Mapped[int] = mapped_column(Integer, default=1)
    use_embeddings: Mapped[bool] = mapped_column(Boolean, default=False)
    remote_files: Mapped[list] = mapped_column(JSON, default=list)
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MaterialSection(Base):
    __tablename__ = "material_sections"
    __table_args__ = (
        UniqueConstraint("asset_id", "section_key"),
        ForeignKeyConstraint(["space_id", "asset_id"], ["material_assets.space_id", "material_assets.id"]),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    space_id: Mapped[str] = mapped_column(String(36), index=True)
    asset_id: Mapped[str] = mapped_column(String(36), index=True)
    section_key: Mapped[str] = mapped_column(String(80))
    data: Mapped[dict] = mapped_column(JSON)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    embedding_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)


class MaterialJob(Base):
    __tablename__ = "material_jobs"
    __table_args__ = (
        UniqueConstraint("space_id", "request_key"),
        ForeignKeyConstraint(["space_id", "asset_id"], ["material_assets.space_id", "material_assets.id"]),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    space_id: Mapped[str] = mapped_column(String(36), index=True)
    asset_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="index")
    request_key: Mapped[str] = mapped_column(String(100))
    generation: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(30), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReviewState(Base):
    __tablename__ = "review_states"
    __table_args__ = (
        UniqueConstraint("space_id", "concept_id"),
        ForeignKeyConstraint(["user_id", "space_id"], ["study_spaces.user_id", "study_spaces.id"]),
        ForeignKeyConstraint(
            ["space_id", "concept_id"], ["knowledge_concepts.space_id", "knowledge_concepts.key"]
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36))
    space_id: Mapped[str] = mapped_column(String(36))
    concept_id: Mapped[str] = mapped_column(String(80))
    card: Mapped[dict] = mapped_column(JSON)
    due: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    parameter_version: Mapped[str] = mapped_column(String(80), default="fsrs-defaults-v1")


class ReviewSession(Base):
    __tablename__ = "review_sessions"
    __table_args__ = (
        UniqueConstraint("space_id", "request_key"),
        UniqueConstraint("space_id", "active_concept"),
        ForeignKeyConstraint(["user_id", "space_id"], ["study_spaces.user_id", "study_spaces.id"]),
        ForeignKeyConstraint(
            ["space_id", "concept_id"], ["knowledge_concepts.space_id", "knowledge_concepts.key"]
        ),
        ForeignKeyConstraint(["space_id", "item_id"], ["assessment_items.space_id", "assessment_items.id"]),
        ForeignKeyConstraint(["space_id", "lesson_id"], ["lessons.space_id", "lessons.id"]),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36))
    space_id: Mapped[str] = mapped_column(String(36))
    concept_id: Mapped[str] = mapped_column(String(80))
    active_concept: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lesson_id: Mapped[str] = mapped_column(String(36))
    item_id: Mapped[str] = mapped_column(String(36), unique=True)
    request_key: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReviewLogRecord(Base):
    __tablename__ = "review_logs"
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "space_id"], ["study_spaces.user_id", "study_spaces.id"]),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36))
    space_id: Mapped[str] = mapped_column(String(36))
    state_id: Mapped[str] = mapped_column(ForeignKey("review_states.id"))
    event_id: Mapped[str] = mapped_column(ForeignKey("learning_events.id"), unique=True)
    log: Mapped[dict] = mapped_column(JSON)
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    parameter_version: Mapped[str] = mapped_column(String(80))


class MaintenanceOperation(Base):
    __tablename__ = "maintenance_operations"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LearningIntent(Base):
    __tablename__ = "learning_intents"
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "space_id"], ["study_spaces.user_id", "study_spaces.id"]),
    )
    space_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class ChatTurn(Base):
    __tablename__ = "chat_turns"
    __table_args__ = (
        UniqueConstraint("space_id", "id"),
        UniqueConstraint("space_id", "request_key"),
        UniqueConstraint("active_space_id"),
        ForeignKeyConstraint(["user_id", "space_id"], ["study_spaces.user_id", "study_spaces.id"]),
        ForeignKeyConstraint(["user_id", "provider_id"], ["provider_configs.user_id", "provider_configs.id"]),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    space_id: Mapped[str] = mapped_column(String(36), index=True)
    active_space_id: Mapped[str | None] = mapped_column(ForeignKey("study_spaces.id"), nullable=True)
    provider_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    request_key: Mapped[str] = mapped_column(String(100))
    request_digest: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="processing")
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    baseline: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PlanRevision(Base):
    __tablename__ = "plan_revisions"
    __table_args__ = (
        UniqueConstraint("space_id", "version"),
        UniqueConstraint("turn_id"),
        ForeignKeyConstraint(["user_id", "space_id"], ["study_spaces.user_id", "study_spaces.id"]),
        ForeignKeyConstraint(["space_id", "turn_id"], ["chat_turns.space_id", "chat_turns.id"]),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    space_id: Mapped[str] = mapped_column(String(36), index=True)
    turn_id: Mapped[str] = mapped_column(String(36))
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def activity_owner():
    return ForeignKeyConstraint(["user_id", "space_id"], ["study_spaces.user_id", "study_spaces.id"])


class ActivityFields:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    space_id: Mapped[str] = mapped_column(String(36), index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PeriodicJob(ActivityFields, Base):
    __tablename__ = "periodic_jobs"
    __table_args__ = (activity_owner(), UniqueConstraint("space_id", "kind", "period_key"))
    kind: Mapped[str] = mapped_column(String(30))
    period_key: Mapped[str] = mapped_column(String(80))
    generation: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    executions: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)


class DailyPlan(ActivityFields, Base):
    __tablename__ = "daily_plans"
    __table_args__ = (
        activity_owner(),
        UniqueConstraint("space_id", "local_date"),
        UniqueConstraint("space_id", "id"),
    )
    local_date: Mapped[str] = mapped_column(String(10))
    timezone: Mapped[str] = mapped_column(String(64))


class DailyTask(ActivityFields, Base):
    __tablename__ = "daily_tasks"
    __table_args__ = (
        activity_owner(),
        UniqueConstraint("space_id", "task_key"),
        UniqueConstraint("space_id", "active_cycle_key"),
        ForeignKeyConstraint(["space_id", "plan_id"], ["daily_plans.space_id", "daily_plans.id"]),
        ForeignKeyConstraint(["space_id", "lesson_id"], ["lessons.space_id", "lessons.id"]),
    )
    plan_id: Mapped[str] = mapped_column(String(36))
    task_key: Mapped[str] = mapped_column(String(200))
    concept_id: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(30))
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=15)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    active_cycle_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    lesson_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class LearningSuggestion(ActivityFields, Base):
    __tablename__ = "learning_suggestions"
    __table_args__ = (activity_owner(), UniqueConstraint("space_id", "event_key"))
    event_key: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default="pending")


class InboxMessage(ActivityFields, Base):
    __tablename__ = "inbox_messages"
    __table_args__ = (activity_owner(), UniqueConstraint("space_id", "event_key"))
    event_key: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(30))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WeeklySummary(ActivityFields, Base):
    __tablename__ = "weekly_summaries"
    __table_args__ = (activity_owner(), UniqueConstraint("space_id", "week_start"))
    week_start: Mapped[str] = mapped_column(String(10))
    timezone: Mapped[str] = mapped_column(String(64))


class AnalysisRun(ActivityFields, Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (activity_owner(), UniqueConstraint("space_id", "request_key"))
    request_key: Mapped[str] = mapped_column(String(100))
    request_digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="processing")
    provider_id: Mapped[str] = mapped_column(String(36))
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    budget_date: Mapped[str] = mapped_column(String(10))
    reserved_tokens: Mapped[int] = mapped_column(Integer)
    usage_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AnalysisDailyUsage(Base):
    __tablename__ = "analysis_daily_usage"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    utc_date: Mapped[str] = mapped_column(String(10), primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, default=0)
    occupied_tokens: Mapped[int] = mapped_column(Integer, default=0)
    actual_tokens: Mapped[int] = mapped_column(Integer, default=0)
    unknown_calls: Mapped[int] = mapped_column(Integer, default=0)
