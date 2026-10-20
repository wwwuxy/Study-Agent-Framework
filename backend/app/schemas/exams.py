"""Strict external-paper contracts; model output is data, never an instruction."""

from datetime import date
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.domain import StrictModel

Result = Literal["correct", "incorrect", "partial", "unanswered", "uncertain"]
Confidence = Literal["high", "medium", "low"]


class AttachmentManifest(StrictModel):
    client_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    filename: str = Field(min_length=1, max_length=200)
    mime_type: Literal["application/pdf", "image/jpeg", "image/png"]
    size_bytes: int = Field(gt=0, strict=True)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ExamCreate(StrictModel):
    name: str = Field(default="已批改试卷", min_length=1, max_length=200)
    exam_date: date | None = None
    attachments: list[AttachmentManifest] = Field(min_length=1, max_length=20)
    idempotency_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")

    @model_validator(mode="after")
    def valid_manifest(self):
        if len({a.client_id for a in self.attachments}) != len(self.attachments):
            raise ValueError("附件标识重复")
        if any(a.mime_type == "application/pdf" for a in self.attachments) and len(self.attachments) != 1:
            raise ValueError("一份试卷只能使用一个 PDF 或一组图片")
        return self


class ExamStart(StrictModel):
    consent: bool = False
    idempotency_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")


class ExamRetry(ExamStart):
    pass


class RecognizedQuestion(StrictModel):
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    number: str = Field(min_length=1, max_length=100)
    parent_id: str | None = Field(default=None, max_length=80)
    source_id: str = Field(min_length=1, max_length=80)
    page: int | None = Field(default=None, ge=1)
    prompt: str = Field(default="", max_length=12000)
    student_answer: str = Field(default="", max_length=8000)
    teacher_marks: str = Field(default="", max_length=8000)
    teacher_mark_clear: bool = False
    teacher_result: Result | None = None
    result: Result = "uncertain"
    score: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    max_score: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    recognition_confidence: Confidence = "low"
    mapping_confidence: Confidence = "low"
    concept_ids: list[str] = Field(default_factory=list, max_length=10)
    unmapped_concepts: list[str] = Field(default_factory=list, max_length=10)
    notes: list[str] = Field(default_factory=list, max_length=20)
    leaf_order: int = Field(default=0, ge=0, le=200)

    @field_validator("score", "max_score", mode="before")
    @classmethod
    def numeric_scores(cls, value):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise ValueError("分值必须是有限数值")
        return value

    @model_validator(mode="after")
    def score_range(self):
        if self.score is not None and self.max_score is not None and self.score > self.max_score:
            raise ValueError("得分不能超过满分")
        return self


class ExamRecognition(StrictModel):
    title: str = Field(default="", max_length=200)
    coverage_complete: bool = False
    coverage_note: str = Field(default="", max_length=2000)
    stated_score: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    stated_max_score: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    questions: list[RecognizedQuestion] = Field(min_length=1, max_length=200)

    @field_validator("stated_score", "stated_max_score", mode="before")
    @classmethod
    def numeric_scores(cls, value):
        return RecognizedQuestion.numeric_scores(value)


class ExamSuggestion(StrictModel):
    concept_ids: list[str] = Field(default_factory=list, max_length=10)
    question_ids: list[str] = Field(default_factory=list, max_length=20)
    reason: str = Field(max_length=2000)
    action: str = Field(max_length=2000)


class ExamAdvice(StrictModel):
    summary: str = Field(max_length=8000)
    suggestions: list[ExamSuggestion] = Field(default_factory=list, max_length=12)


class ExamQuestionPatch(StrictModel):
    expected_version: int = Field(ge=1)
    result: Result | None = None
    score: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    max_score: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    concept_ids: list[str] | None = Field(default=None, max_length=10)
    idempotency_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    _numeric = field_validator("score", "max_score", mode="before")(
        RecognizedQuestion.numeric_scores.__func__
    )


class ExamCapabilities(StrictModel):
    provider_name: str
    pdf: bool
    images: list[str]
    max_bytes: int
    max_total_bytes: int
    max_images: int
    max_questions: int
    is_demo: bool = False
    notice: str = "试卷由当前用户模型识别；费用和远端保留遵循所选服务商政策。"


class ExamAttachmentView(StrictModel):
    id: str
    client_id: str
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    position: int
    received: bool


class ExamQuestionView(StrictModel):
    id: str
    version: int
    original: RecognizedQuestion
    current: RecognizedQuestion
    event_id: str | None
    exclusion_reason: str | None


class ExamDetail(StrictModel):
    id: str
    study_space_id: str
    name: str
    exam_date: str | None
    status: str
    version: int
    created_at: str
    imported_at: str | None
    attachments: list[ExamAttachmentView] = Field(default_factory=list)
    questions: list[ExamQuestionView] = Field(default_factory=list)
    task: dict | None = None
    report: dict = Field(default_factory=dict)
    effective_evidence_count: int = 0
    before: dict = Field(default_factory=dict)
    after: dict = Field(default_factory=dict)
    is_demo: bool = False
    cleanup_warning: str | None = None


class ExamPage(StrictModel):
    items: list[ExamDetail]
    next_cursor: str | None
