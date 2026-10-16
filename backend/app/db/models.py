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
    provider_id: Mapped[str] = mapped_column(String(36), index=True)
    goal: Mapped[str] = mapped_column(Text)
    target_date: Mapped[str | None] = mapped_column(String(10))
    daily_minutes: Mapped[int] = mapped_column(Integer, default=30)
    expected_level: Mapped[str] = mapped_column(String(200), default="基础掌握")
    allow_general_knowledge: Mapped[bool] = mapped_column(Boolean, default=False)
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


# Guard even direct SQL writes: historical learning evidence is immutable.
for operation in ("UPDATE", "DELETE"):
    event.listen(
        LearningEvent.__table__,
        "after_create",
        DDL(
            f"CREATE TRIGGER learning_events_no_{operation.lower()} BEFORE {operation} ON learning_events "
            "BEGIN SELECT RAISE(ABORT, 'learning_events are append-only'); END"
        ).execute_if(dialect="sqlite"),
    )

event.listen(
    LearningEvent.__table__,
    "after_create",
    DDL("""
CREATE FUNCTION reject_learning_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'learning_events are append-only'; END; $$
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
