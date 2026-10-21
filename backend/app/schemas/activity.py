from typing import Literal

from pydantic import Field

from app.schemas.domain import StrictModel


class Page[T](StrictModel):
    items: list[T]
    next_cursor: str | None = None


class DailyTaskResponse(StrictModel):
    id: str
    study_space_id: str
    plan_id: str
    concept_id: str
    name: str
    action: str
    estimated_minutes: int
    status: Literal["pending", "in_progress", "completed", "skipped", "postponed", "superseded"]
    blocking_reason: str | None = None
    reason: str
    lesson_id: str | None = None
    item_ids: list[str] = Field(default_factory=list)
    created_at: str


class TaskAllocation(StrictModel):
    task: DailyTaskResponse
    allocated_minutes: int
    carried_over: bool = False


class DailyPlanResponse(StrictModel):
    id: str
    study_space_id: str
    local_date: str
    timezone: str
    budget_minutes: int
    intent_version: int
    fingerprint: str
    as_of: str
    warning: str | None = None
    slots: list[TaskAllocation]
    backlog: list[DailyTaskResponse]


class TodayResponse(StrictModel):
    plan: DailyPlanResponse | None
    reason: str | None = None


class TaskStartResponse(StrictModel):
    task: DailyTaskResponse
    execution_kind: Literal["lesson", "diagnostic"]
    lesson_id: str | None = None
    item_ids: list[str] = Field(default_factory=list)


class SuggestionResponse(StrictModel):
    id: str
    study_space_id: str
    status: Literal["pending", "accepted", "skipped", "expired"]
    kind: str
    title: str
    reason: str
    fingerprint: str
    created_at: str


class InboxResponse(StrictModel):
    id: str
    study_space_id: str
    kind: Literal["due", "deviation", "weekly"]
    title: str
    summary: str
    source_kind: Literal["daily_plan", "suggestion", "weekly_summary"]
    source_id: str
    read_at: str | None = None
    created_at: str


class GoalForecast(StrictModel):
    status: Literal["estimated", "insufficient_data", "achieved"]
    target_date: str | None = None
    remaining_concepts: int
    sample_weeks: int
    weekly_gains: list[int]
    earliest: str | None = None
    latest: str | None = None
    reason: str
    uncertainty: str


class Fraction(StrictModel):
    numerator: int
    denominator: int
    rate: float | None
    reason: str | None = None


class WeeklySummaryResponse(StrictModel):
    id: str
    study_space_id: str
    week_start: str
    timezone: str
    window_start: str
    window_end: str
    as_of: str
    fingerprint: str
    preview: bool = False
    intent_version: int = 0
    due_reviews: int = 0
    answers: int
    independent: int
    assisted: int
    uncertain: int
    before_mastered: int
    after_mastered: int
    evidence_count: int
    error_concepts: list[str]
    skipped_tasks: int
    review_retention: Fraction
    task_completion: Fraction
    forecast: GoalForecast
    notice: str


class ActivityJobResponse(StrictModel):
    id: str
    study_space_id: str
    kind: Literal["daily_coordinate", "weekly_summary"]
    status: Literal["queued", "running", "retry_wait", "succeeded", "dead_letter", "cancelled"]
    attempts: int
    executions: int
    available_at: str
    error_code: str | None = None
    error_message: str | None = None
    created_at: str


class UnreadCountResponse(StrictModel):
    count: int
