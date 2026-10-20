from dataclasses import dataclass

from app.schemas.exams import ExamAdvice, ExamRecognition


@dataclass(frozen=True)
class ExamClaim:
    job_id: str
    diagnostic_id: str
    user_id: str
    space_id: str
    token: str
    generation: int


@dataclass(frozen=True)
class ExamCheckpoint:
    recognition: ExamRecognition | None
    advice: ExamAdvice | None
    provider_fingerprint: str
    concept_fingerprint: str
