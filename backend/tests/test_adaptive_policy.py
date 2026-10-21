from datetime import UTC, datetime, timedelta

from app.planning.policy import choose_action


def nodes():
    return [
        {"key": "a", "prerequisites": [], "importance": 1, "minutes": 15},
        {"key": "b", "prerequisites": ["a"], "importance": 5, "minutes": 15},
    ]


def test_unmet_prerequisites_win_over_importance_or_due_review():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    result = choose_action(
        nodes(),
        {"a": {"status": "unknown"}, "b": {"status": "unknown"}},
        {"b": {"status": "due", "due": (now - timedelta(days=5)).isoformat()}},
        [],
        10,
        now=now,
    )
    assert result["concept_ids"] == ["a"]
    assert result["action"] == "DIAGNOSE"
    assert result["estimated_minutes"] <= 10


def test_due_review_affects_order_but_not_mastery():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    states = {
        "a": {
            "status": "mastered",
            "mastery_estimate": 0.9,
            "evidence_count": 5,
            "evidence_confidence": "high",
        },
        "b": {
            "status": "mastered",
            "mastery_estimate": 0.9,
            "evidence_count": 5,
            "evidence_confidence": "high",
        },
    }
    result = choose_action(
        nodes(),
        states,
        {"a": {"status": "due", "due": (now - timedelta(days=99)).isoformat()}},
        [],
        30,
        now=now,
    )
    assert result["action"] == "REVIEW" and result["concept_ids"] == ["a"]
    assert states["a"]["status"] == "mastered"
    assert result["score_breakdown"]["review_due"] > 0


def test_diagnostic_budget_does_not_loop_finished_initial_diagnosis():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    events = [{"type": "diagnostic_submitted", "assessment_item_id": str(i)} for i in range(5)]
    result = choose_action(nodes(), {}, {}, events, 30, now=now)
    assert result["action"] == "LEARN_CONCEPT"
    assert result["policy_version"] == "policy_v3"
