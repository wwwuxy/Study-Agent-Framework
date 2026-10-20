import pytest

from app.exam_diagnostics.recognition import normalize
from app.providers.base import ProviderError
from app.schemas.exams import ExamRecognition


def test_teacher_marks_take_precedence_and_conflicts_stay_uncertain(recognition_payload, exam_env):
    q = recognition_payload["questions"][0]
    q["teacher_result"] = "incorrect"
    row = normalize(ExamRecognition.model_validate(recognition_payload), {"a1"}, set(exam_env.concepts))
    assert row.questions[0].result == "uncertain"
    assert not row.questions[0].teacher_mark_clear


def test_unowned_sources_and_concepts_rejected(recognition_payload, exam_env):
    recognition_payload["questions"][0]["concept_ids"] = ["foreign"]
    with pytest.raises(ProviderError):
        normalize(ExamRecognition.model_validate(recognition_payload), {"a1"}, set(exam_env.concepts))
