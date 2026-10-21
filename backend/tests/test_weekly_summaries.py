from datetime import UTC, datetime, timedelta

from conftest import provider, register, space


def test_forecast_uses_all_complete_weeks_and_no_fake_precision():
    from app.activity.weekly import forecast_goal

    now = datetime(2026, 10, 19, tzinfo=UTC)
    estimate = forecast_goal(8, [2, 4], now, None)
    assert estimate.earliest == "2026-11-02"
    assert estimate.latest == "2026-11-16"
    for gains in ([0, 4], [-1, 4], [4], []):
        assert forecast_goal(8, gains, now, None).status == "insufficient_data"
    assert forecast_goal(0, [], now, None).status == "achieved"


def test_weekly_report_ignores_later_answers_and_persists_snapshot(client):
    from app.activity.calendar import previous_week
    from app.activity.weekly import publish_week
    from app.db.models import LearningEvent, utcnow

    register(client)
    sid = space(client, provider(client))
    uid = client.get("/api/v1/auth/me").json()["id"]
    now = utcnow()
    period = previous_week(now, "Asia/Shanghai")
    factory = client.app.state.session_factory
    with factory.begin() as db:
        for index in range(2):
            db.add(
                LearningEvent(
                    user_id=uid,
                    space_id=sid,
                    type="assessment_submitted",
                    idempotency_key=f"week{index}",
                    occurred_at=period.start + timedelta(days=index + 1),
                    data={
                        "assessment_item_id": f"q{index}",
                        "concept_ids": ["os"],
                        "is_correct": True,
                        "confidence": "high",
                        "difficulty": 2,
                        "assistance_level": "none",
                        "evaluator": "deterministic_answer_key",
                    },
                )
            )
        db.add(
            LearningEvent(
                user_id=uid,
                space_id=sid,
                type="assessment_submitted",
                idempotency_key="later",
                occurred_at=period.end,
                data={
                    "assessment_item_id": "late",
                    "concept_ids": ["os"],
                    "is_correct": False,
                    "confidence": "high",
                    "difficulty": 2,
                    "assistance_level": "none",
                    "evaluator": "deterministic_answer_key",
                },
            )
        )
    report = publish_week(factory, uid, sid, period, now)
    assert report.answers == 2
    assert report.after_mastered == 1
    assert report.error_concepts == []
    assert report.review_retention.rate is None
    assert publish_week(factory, uid, sid, period, now + timedelta(days=1)) == report
    root = f"/api/v1/study-spaces/{sid}"
    response = client.get(root + "/weekly-summaries")
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["id"] == report.id
    assert len(client.get("/api/v1/inbox").json()["items"]) == 1


def test_empty_week_read_is_side_effect_free(client):
    register(client)
    sid = space(client, provider(client))
    root = f"/api/v1/study-spaces/{sid}"
    before = client.get(root + "/events").json()
    result = client.get(root + "/weekly-summaries/current")
    assert result.status_code == 200, result.text
    assert result.json()["task_completion"]["rate"] is None
    assert result.json()["forecast"]["status"] == "insufficient_data"
    assert client.get(root + "/events").json() == before
