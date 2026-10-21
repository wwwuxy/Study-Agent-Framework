from datetime import timedelta

from conftest import provider, register, space
from sqlalchemy import select


def ready(client):
    register(client)
    sid = space(client, provider(client))
    return sid, client.get("/api/v1/auth/me").json()["id"]


def test_daily_plan_budget_prerequisites_and_read_only(client):
    from app.activity.daily import coordinate_day, today_plan
    from app.db.models import LearningEvent, utcnow

    sid, uid = ready(client)
    factory = client.app.state.session_factory
    with factory() as db:
        before = len(list(db.scalars(select(LearningEvent))))
        assert today_plan(db, uid, sid, utcnow()).plan is None
    plan = coordinate_day(factory, uid, sid, utcnow())
    assert 1 <= len(plan.slots) <= 6
    assert sum(s.allocated_minutes for s in plan.slots) <= 30
    assert all(s.task.concept_id == "os" for s in plan.slots)
    assert coordinate_day(factory, uid, sid, utcnow()).id == plan.id
    with factory() as db:
        assert len(list(db.scalars(select(LearningEvent)))) == before


def test_task_start_restores_diagnostics_and_real_completion(client):
    from app.activity.daily import coordinate_day
    from app.db.models import utcnow

    sid, uid = ready(client)
    plan = coordinate_day(client.app.state.session_factory, uid, sid, utcnow())
    root = f"/api/v1/study-spaces/{sid}"
    task = plan.slots[0].task
    start = client.post(root + f"/tasks/{task.id}/start", json={"idempotency_key": "start"})
    assert start.status_code == 200, start.text
    assert start.json()["execution_kind"] == "diagnostic"
    assert (
        client.post(root + f"/tasks/{task.id}/start", json={"idempotency_key": "start"}).json()
        == start.json()
    )
    assert (
        client.post(root + f"/tasks/{task.id}/complete", json={"idempotency_key": "complete"}).status_code
        == 409
    )
    questions = client.post(root + "/diagnostics").json()["items"]
    for i, q in enumerate(questions):
        assert (
            client.post(
                root + "/attempts", json={"item_id": q["id"], "answer": "A", "idempotency_key": f"a{i}"}
            ).status_code
            == 201
        )
    result = client.post(root + f"/tasks/{task.id}/complete", json={"idempotency_key": "complete"})
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "completed"
    refreshed = coordinate_day(client.app.state.session_factory, uid, sid, utcnow())
    assert any(slot.task.id == task.id and slot.task.status == "completed" for slot in refreshed.slots)


def test_skips_postpone_and_cross_day_carryover_do_not_modify_evidence(client):
    from app.activity.daily import coordinate_day
    from app.db.models import DailyTask, ReviewState, utcnow

    sid, uid = ready(client)
    factory = client.app.state.session_factory
    now = utcnow()
    plan = coordinate_day(factory, uid, sid, now)
    tid = plan.slots[0].task.id
    root = f"/api/v1/study-spaces/{sid}"
    before = client.get(root + "/profile").json()
    with factory() as db:
        cards = [r.card for r in db.scalars(select(ReviewState))]
    assert client.post(root + f"/tasks/{tid}/skip", json={"idempotency_key": "skip"}).status_code == 200
    assert client.get(root + "/profile").json() == before
    with factory() as db:
        assert [r.card for r in db.scalars(select(ReviewState))] == cards
    with factory.begin() as db:
        row = db.get(DailyTask, tid)
        row.status = "in_progress"
    tomorrow = coordinate_day(factory, uid, sid, now + timedelta(days=1))
    assert tomorrow.slots[0].task.id == tid
    assert tomorrow.slots[0].task.plan_id == plan.id
    assert tomorrow.slots[0].carried_over


def test_other_account_cannot_operate_daily_task(client):
    from app.activity.daily import coordinate_day
    from app.db.models import utcnow

    sid, uid = ready(client)
    tid = coordinate_day(client.app.state.session_factory, uid, sid, utcnow()).slots[0].task.id
    client.post("/api/v1/auth/logout")
    register(client, "bob")
    root = f"/api/v1/study-spaces/{sid}"
    assert client.post(root + f"/tasks/{tid}/start", json={"idempotency_key": "x"}).status_code == 404


def test_postponed_task_retains_origin_and_cannot_restart_closed_execution(client):
    from app.activity.daily import coordinate_day
    from app.db.models import DailyTask, utcnow

    sid, uid = ready(client)
    factory, now = client.app.state.session_factory, utcnow()
    plan = coordinate_day(factory, uid, sid, now)
    task = plan.slots[0].task
    root = f"/api/v1/study-spaces/{sid}/tasks/{task.id}"
    assert client.post(root + "/start", json={"idempotency_key": "start"}).status_code == 200
    assert client.post(root + "/postpone", json={"idempotency_key": "later"}).status_code == 200
    assert client.post(root + "/start", json={"idempotency_key": "different"}).status_code == 409
    next_plan = coordinate_day(factory, uid, sid, now + timedelta(days=1))
    with factory() as db:
        assert db.get(DailyTask, next_plan.slots[0].task.id).data["origin_task_id"] == task.id
