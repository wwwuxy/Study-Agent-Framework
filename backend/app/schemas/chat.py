from datetime import date
from typing import Any, Literal

from pydantic import Field, model_validator

from app.schemas.api import IdempotentRequest
from app.schemas.domain import KnowledgeConcept, StrictModel


class ChatSend(IdempotentRequest):
    content: str = Field(min_length=1, max_length=4000)
    retry: bool = False


class RequirementPatch(StrictModel):
    goal: str | None = Field(default=None, min_length=2, max_length=2000)
    daily_minutes: int | None = Field(default=None, ge=5, le=480)
    target_date: date | None = None
    expected_level: str | None = Field(default=None, min_length=1, max_length=200)
    included_concept_ids: list[str] | None = Field(default=None, min_length=1, max_length=60)
    priority_concept_ids: list[str] | None = Field(default=None, max_length=60)
    deferred_concept_ids: list[str] | None = Field(default=None, max_length=60)
    teaching_preferences: str | None = Field(default=None, max_length=2000)
    learner_notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def nonnullable(self):
        for key in self.model_fields_set - {"target_date", "included_concept_ids"}:
            if getattr(self, key) is None:
                raise ValueError("该需求字段不能为null")
        return self


class PlanStage(StrictModel):
    title: str = Field(min_length=1, max_length=160)
    objective: str = Field(min_length=1, max_length=1000)
    concept_ids: list[str] = Field(min_length=1, max_length=30)
    suggested_sessions: int = Field(ge=1, le=60)


class ChatDecision(StrictModel):
    kind: Literal["reply", "clarify", "update_plan"]
    reply: str = Field(min_length=1, max_length=8000)
    patch: RequirementPatch | None = None
    added_concepts: list[KnowledgeConcept] = Field(default_factory=list, max_length=12)
    stages: list[PlanStage] | None = Field(default=None, max_length=12)
    interrupt_current: bool = False
    reason: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def valid_decision(self):
        if self.kind != "update_plan" and (
            self.patch is not None or self.added_concepts or self.stages is not None or self.interrupt_current
        ):
            raise ValueError("普通回复不能修改计划")
        if self.kind == "update_plan" and not self.reason:
            raise ValueError("计划修改必须有原因")
        return self


class PlanChange(StrictModel):
    field: str
    before: Any = None
    after: Any = None
    reason: str


class ChatTurnResponse(StrictModel):
    id: str
    study_space_id: str
    content: str
    idempotency_key: str
    reply: str | None = None
    status: Literal["processing", "completed", "failed", "conflict", "cancelled"]
    outcome: (
        Literal["applied", "not_changed", "clarification_needed", "failed", "conflict", "cancelled"] | None
    ) = None
    changes: list[PlanChange] = Field(default_factory=list)
    revision_id: str | None = None
    plan: dict | None = None
    retry_allowed: bool = False
    error_code: str | None = None
    error_message: str | None = None
    created_at: str


class ChatTurnPage(StrictModel):
    items: list[ChatTurnResponse]
    next_cursor: str | None = None


class PlanRevisionResponse(StrictModel):
    id: str
    version: int
    turn_id: str
    before: dict
    after: dict
    changes: list[PlanChange]
    created_at: str


class PlanRevisionPage(StrictModel):
    items: list[PlanRevisionResponse]
    next_cursor: str | None = None
