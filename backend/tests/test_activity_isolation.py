from datetime import timedelta

from conftest import provider, register, space
from sqlalchemy import select

from app.db.models import LearningEvent, utcnow


def test_account_and_parent_boundaries_preserve_private_data(client):
    from app.activity.scheduler import enqueue_cycles

    register(client)
    pid = provider(client)
    sid = space(client, pid, key="same-space-key")
    root = f"/api/v1/study-spaces/{sid}"
    uid = client.get("/api/v1/auth/me").json()["id"]
    with client.app.state.session_factory.begin() as db:
        db.add(
            LearningEvent(
                user_id=uid,
                space_id=sid,
                type="lesson_viewed",
                idempotency_key="old",
                occurred_at=utcnow() - timedelta(days=4),
                data={},
            )
        )
    plan = client.post(root + "/daily-plans/refresh", json={"idempotency_key": "same-key"}).json()
    tid = plan["slots"][0]["task"]["id"]
    gid = client.get(root + "/suggestions").json()[0]["id"]
    week = client.post(root + "/weekly-summaries/refresh", json={"idempotency_key": "same-key"}).json()
    aid = client.post(
        root + "/analyses",
        json={"source_kind": "daily_plan", "source_id": plan["id"], "idempotency_key": "same-key"},
    ).json()["id"]
    msg = client.get("/api/v1/inbox").json()["items"][0]["id"]
    enqueue_cycles(client.app.state.session_factory, utcnow())
    job = client.get("/api/v1/activity-jobs").json()["items"][0]["id"]
    a_summary = client.get(root + "/weekly-summaries/" + week["id"]).json()
    client.post("/api/v1/auth/logout")
    register(client, "bob")
    bpid = provider(client)
    bsid = space(client, bpid, key="same-space-key")
    broot = f"/api/v1/study-spaces/{bsid}"
    before = client.get(broot + "/events").json()
    for path in (
        "/daily-plans/today",
        "/tasks",
        "/suggestions",
        "/weekly-summaries",
        "/weekly-summaries/current",
        "/weekly-summaries/" + week["id"],
        "/analyses",
        "/analyses/" + aid,
        "/concepts",
        "/profile",
        "/events",
        "/materials",
        "/plan",
        "/chat/turns",
        "/reviews",
    ):
        assert client.get(root + path).status_code == 404, path
    for path in (
        f"/tasks/{tid}/start",
        f"/tasks/{tid}/complete",
        f"/tasks/{tid}/skip",
        f"/tasks/{tid}/postpone",
        f"/suggestions/{gid}/accept",
        f"/suggestions/{gid}/skip",
    ):
        for prefix in (root, broot):
            result = client.post(prefix + path, json={"idempotency_key": "same-key"})
            assert result.status_code == 404, (path, result.text)
    for path in ("/weekly-summaries/" + week["id"], "/analyses/" + aid):
        assert client.get(broot + path).status_code == 404
    result = client.post(
        broot + "/analyses",
        json={"source_kind": "daily_plan", "source_id": plan["id"], "idempotency_key": "same-key"},
    )
    assert result.status_code == 404
    for path in (f"/inbox/{msg}/read", f"/activity-jobs/{job}/retry"):
        assert client.post("/api/v1" + path, json={"idempotency_key": "same-key"}).status_code == 404
    assert client.get("/api/v1/inbox").json()["items"] == []
    assert client.get("/api/v1/activity-jobs").json()["items"] == []
    assert client.get("/api/v1/analysis-usage").json()["calls"] == 0
    assert client.get(broot + "/events").json() == before
    bplan = client.post(broot + "/daily-plans/refresh", json={"idempotency_key": "same-key"}).json()
    result = client.post(
        broot + "/analyses",
        json={"source_kind": "daily_plan", "source_id": bplan["id"], "idempotency_key": "same-key"},
    )
    assert result.status_code == 201 and result.json()["id"] != aid
    client.post("/api/v1/auth/logout")
    for path in ("/inbox", "/activity-jobs", "/analysis-usage", root + "/tasks"):
        assert client.get(path if path.startswith("/api") else "/api/v1" + path).status_code == 401
    client.post("/api/v1/auth/login", json={"username": "alice", "password": "strong-password-2026"})
    assert client.get(root + "/weekly-summaries/" + week["id"]).json() == a_summary
    assert client.get("/api/v1/analysis-usage").json()["calls"] == 1
    with client.app.state.session_factory() as db:
        assert list(db.scalars(select(LearningEvent).where(LearningEvent.space_id == sid)))
