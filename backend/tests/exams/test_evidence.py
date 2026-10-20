from datetime import UTC, date, datetime

from app.exam_diagnostics.evidence import assessment_time, event_payload, qualify
from app.learner.evidence import observations_for
from app.learner.service import compute_states
from app.schemas.exams import RecognizedQuestion


def question(**kw):
    data = {
        "key": "q1",
        "number": "1",
        "source_id": "a1",
        "teacher_marks": "✓",
        "teacher_mark_clear": True,
        "teacher_result": "correct",
        "result": "correct",
        "recognition_confidence": "high",
        "mapping_confidence": "high",
        "concept_ids": ["c"],
    }
    return RecognizedQuestion(**(data | kw))


def test_only_clear_single_concept_teacher_results_are_observations():
    q = question()
    now = datetime(2026, 10, 20, 3, tzinfo=UTC)
    raw = event_payload("e", q, now, None) | {
        "type": "exam_question_imported",
        "event_id": "event1",
        "occurred_at": now.isoformat(),
    }
    assert qualify(q) == (True, None)
    batch = observations_for("c", [raw])
    assert len(batch.observations) == 1
    result = compute_states([{"key": "c"}], [raw])["c"]
    assert result["status"] == "learning" and result["independent_correct_count"] == 0
    for altered in [
        question(result="partial"),
        question(concept_ids=["a", "c"]),
        question(recognition_confidence="low"),
        question(teacher_mark_clear=False),
    ]:
        assert not qualify(altered)[0]


def test_historical_dates_and_unknown_provenance():
    now = datetime(2026, 10, 20, 3, tzinfo=UTC)
    stamp, precision = assessment_time(date(2026, 10, 19), "Asia/Shanghai", now)
    assert stamp == datetime(2026, 10, 19, 4, tzinfo=UTC) and precision == "date"
    assert assessment_time(date(2026, 10, 20), "Asia/Shanghai", now)[0] == now
    assert assessment_time(None, "Asia/Shanghai", now) == (now, "imported_unknown")
