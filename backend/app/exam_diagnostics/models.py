"""External paper entities are separate from generated online assessment items."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base, new_id, utcnow


class ExamOwner:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    space_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def owner_fk():
    return ForeignKeyConstraint(["user_id", "space_id"], ["study_spaces.user_id", "study_spaces.id"])


def diagnostic_fk():
    return ForeignKeyConstraint(
        ["user_id", "space_id", "diagnostic_id"],
        ["exam_diagnostics.user_id", "exam_diagnostics.space_id", "exam_diagnostics.id"],
    )


class ExamDiagnostic(ExamOwner, Base):
    __tablename__ = "exam_diagnostics"
    __table_args__ = (
        owner_fk(),
        UniqueConstraint("user_id", "space_id", "id"),
        UniqueConstraint("space_id", "request_key"),
        UniqueConstraint("space_id", "verified_files_digest"),
    )
    request_key: Mapped[str] = mapped_column(String(100))
    request_digest: Mapped[str] = mapped_column(String(64))
    verified_files_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    canonical_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    exam_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    generation: Mapped[int] = mapped_column(Integer, default=1)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class ExamAttachment(ExamOwner, Base):
    __tablename__ = "exam_attachments"
    __table_args__ = (owner_fk(), diagnostic_fk(), UniqueConstraint("diagnostic_id", "client_id"))
    diagnostic_id: Mapped[str] = mapped_column(String(36), index=True)
    client_id: Mapped[str] = mapped_column(String(80))
    filename: Mapped[str] = mapped_column(String(200))
    mime_type: Mapped[str] = mapped_column(String(40))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(Integer)
    received: Mapped[bool] = mapped_column(Boolean, default=False)


class ExamQuestion(ExamOwner, Base):
    __tablename__ = "exam_questions"
    __table_args__ = (
        owner_fk(),
        diagnostic_fk(),
        UniqueConstraint("diagnostic_id", "leaf_key"),
        UniqueConstraint("event_id"),
    )
    diagnostic_id: Mapped[str] = mapped_column(String(36), index=True)
    leaf_key: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer, default=1)
    original: Mapped[dict] = mapped_column(JSON)
    current: Mapped[dict] = mapped_column(JSON)
    event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    exclusion_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    revisions: Mapped[dict] = mapped_column(JSON, default=dict)


class ExamJob(ExamOwner, Base):
    __tablename__ = "exam_jobs"
    __table_args__ = (
        owner_fk(),
        diagnostic_fk(),
        UniqueConstraint("diagnostic_id", "request_key"),
        UniqueConstraint("active_space_id"),
    )
    diagnostic_id: Mapped[str] = mapped_column(String(36), index=True)
    request_key: Mapped[str] = mapped_column(String(100))
    request_digest: Mapped[str] = mapped_column(String(64), default="")
    active_space_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="recognize")
    status: Mapped[str] = mapped_column(String(20), default="queued")
    stage: Mapped[str] = mapped_column(String(30), default="queued")
    generation: Mapped[int] = mapped_column(Integer, default=1)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
