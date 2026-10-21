from datetime import timedelta

from conftest import provider, register, space


def test_interruption_never_started_and_inbox_read_survives_refresh(client):
    from app.activity.daily import coordinate_day
    from app.db.models import LearningEvent, utcnow

    register(client)
    sid = space(client, provider(client))
    uid = client.get("/api/v1/auth/me").json()["id"]
    factory = client.app.state.session_factory
    now = utcnow()
    coordinate_day(factory, uid, sid, now)
    root = f"/api/v1/study-spaces/{sid}"
    assert client.get(root + "/suggestions").json() == []
    with factory.begin() as db:
        db.add(
            LearningEvent(
                user_id=uid,
                space_id=sid,
                type="lesson_viewed",
                idempotency_key="old",
                data={},
                occurred_at=now - timedelta(days=4),
            )
        )
    coordinate_day(factory, uid, sid, now)
    suggestions = client.get(root + "/suggestions").json()
    assert suggestions[0]["kind"] == "interruption"
    messages = client.get("/api/v1/inbox").json()["items"]
    assert len(messages) == 1
    mid = messages[0]["id"]
    assert client.post(f"/api/v1/inbox/{mid}/read", json={"idempotency_key": "read"}).status_code == 200
    coordinate_day(factory, uid, sid, now)
    assert client.get("/api/v1/inbox").json()["items"][0]["read_at"]
    assert len(client.get("/api/v1/inbox").json()["items"]) == 1


def test_stale_suggestion_and_other_account_are_rejected(client):
    from app.activity.daily import coordinate_day
    from app.db.models import LearningEvent, LearningIntent, utcnow

    register(client)
    sid = space(client, provider(client))
    uid = client.get("/api/v1/auth/me").json()["id"]
    factory = client.app.state.session_factory
    now = utcnow()
    with factory.begin() as db:
        db.add(
            LearningEvent(
                user_id=uid,
                space_id=sid,
                type="lesson_viewed",
                idempotency_key="old",
                data={},
                occurred_at=now - timedelta(days=4),
            )
        )
    coordinate_day(factory, uid, sid, now)
    root = f"/api/v1/study-spaces/{sid}"
    gid = client.get(root + "/suggestions").json()[0]["id"]
    with factory.begin() as db:
        db.add(LearningIntent(user_id=uid, space_id=sid, version=1, data={"daily_minutes": 15}))
    assert (
        client.post(root + f"/suggestions/{gid}/accept", json={"idempotency_key": "accept"}).status_code
        == 409
    )
    client.post("/api/v1/auth/logout")
    register(client, "bob")
    assert client.post(root + f"/suggestions/{gid}/skip", json={"idempotency_key": "skip"}).status_code == 404
    assert client.get("/api/v1/inbox").json()["items"] == []


def test_forecast_warns_before_future_deadline(client, monkeypatch):
    from app.activity.calendar import local_day
    from app.activity.snapshot import read_snapshot
    from app.activity.suggestions import derive_suggestions
    from app.db.models import StudySpace, utcnow
    from app.schemas.activity import GoalForecast

    register(client)
    sid = space(client, provider(client))
    now = utcnow()
    with client.app.state.session_factory() as db:
        snapshot = read_snapshot(db, db.get(StudySpace, sid), now)
    snapshot.intent["target_date"] = (now + timedelta(days=1)).date().isoformat()
    monkeypatch.setattr(
        "app.activity.weekly.forecast_snapshot",
        lambda *args: GoalForecast(
            status="estimated",
            remaining_concepts=2,
            sample_weeks=2,
            weekly_gains=[1, 1],
            earliest=(now + timedelta(days=14)).date().isoformat(),
            latest=(now + timedelta(days=14)).date().isoformat(),
            reason="slow",
            uncertainty="estimate",
        ),
    )
    assert any(s["kind"] == "deadline" for s in derive_suggestions(snapshot, local_day(now, "Asia/Shanghai")))
