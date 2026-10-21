from datetime import UTC, datetime

import pytest


def observation(item, correct=True, assistance="none", **extra):
    return {
        "type": "assessment_submitted",
        "event_id": item,
        "assessment_item_id": item,
        "concept_ids": ["a"],
        "is_correct": correct,
        "confidence": "high",
        "assistance_level": assistance,
        "difficulty": 2,
        "evaluator": "deterministic_answer_key",
        "occurred_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
        **extra,
    }


def test_native_bkt_updates_and_replays_without_manufacturing_evidence():
    from app.learner.bkt import estimate_bkt
    from app.learner.evidence import observations_for
    from app.learner.parameters import BKTParameters

    events = [observation("1"), observation("2")]
    state = estimate_bkt(observations_for("a", events), BKTParameters())
    assert state["mastery_estimate"] == pytest.approx(0.82)
    assert state["status"] == "mastered"
    assert estimate_bkt(observations_for("a", events + events), BKTParameters()) == state
    assert state["estimator_version"] == "pybkt_v1"


def test_hint_class_is_less_evidence_and_only_independent_answers_promote():
    from app.learner.bkt import estimate_bkt
    from app.learner.evidence import observations_for
    from app.learner.parameters import BKTParameters

    independent = estimate_bkt(observations_for("a", [observation("1")]), BKTParameters())
    assisted = estimate_bkt(observations_for("a", [observation("1", assistance="hint")]), BKTParameters())
    assert 0 < assisted["mastery_estimate"] < independent["mastery_estimate"]
    assert assisted["independent_correct_count"] == 0
    for extra in [
        {"confidence": "low"},
        {"evaluator": "llm_rubric:model"},
        {"concept_ids": ["a", "b"]},
        {"assistance_level": "solution"},
    ]:
        assert (
            estimate_bkt(observations_for("a", [observation("1", **extra)]), BKTParameters())["status"]
            == "unknown"
        )


def test_native_bkt_wrong_answer_and_parameters_are_isolated():
    from app.learner.bkt import estimate_bkt
    from app.learner.evidence import observations_for
    from app.learner.parameters import BKTParameters

    params = BKTParameters()
    events = [observation("1"), observation("2")]
    before = estimate_bkt(observations_for("a", events), params)
    wrong = estimate_bkt(observations_for("a", events + [observation("3", False)]), params)
    assert wrong["status"] == "learning"
    assert wrong["mastery_estimate"] < before["mastery_estimate"]
    assert estimate_bkt(observations_for("a", events), params) == before
