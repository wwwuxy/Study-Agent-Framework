from app.exam_diagnostics.report import summarize
from app.schemas.exams import ExamRecognition, RecognizedQuestion


def test_partial_parents_and_unknown_score_are_not_fabricated():
    row = ExamRecognition(
        coverage_complete=False,
        questions=[
            RecognizedQuestion(key="p", number="1", source_id="a"),
            RecognizedQuestion(
                key="c", number="1a", parent_id="p", source_id="a", result="partial", score=2, max_score=5
            ),
            RecognizedQuestion(key="q", number="2", source_id="a", result="correct"),
        ],
    )
    summary = summarize(row)
    assert summary["counts"]["partial"] == 1 and summary["counts"]["correct"] == 1
    assert summary["total_questions"] == 2
    assert summary["correctness_rate"] is None
    assert summary["verified_score_sum"] == 2
    assert not summary["all_scores_known"]
