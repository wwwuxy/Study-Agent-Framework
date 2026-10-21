import pytest
from conftest import provider, register, space
from sqlalchemy.exc import IntegrityError


def test_activity_child_cannot_reference_other_users_space(client):
    from app.db.models import DailyPlan

    register(client)
    sid = space(client, provider(client))
    first = client.get("/api/v1/auth/me").json()["id"]
    client.post("/api/v1/auth/logout")
    register(client, "bob")
    second = client.get("/api/v1/auth/me").json()["id"]
    with client.app.state.session_factory() as db:
        db.add(DailyPlan(user_id=second, space_id=sid, local_date="2026-10-19", timezone="Asia/Shanghai"))
        with pytest.raises(IntegrityError):
            db.flush()
    assert first != second


def test_task_cannot_reference_another_spaces_plan_or_lesson(client):
    from app.db.models import DailyPlan, DailyTask

    register(client)
    pid = provider(client)
    a, b = space(client, pid), space(client, pid, "b")
    uid = client.get("/api/v1/auth/me").json()["id"]
    with client.app.state.session_factory() as db:
        plan = DailyPlan(user_id=uid, space_id=a, local_date="2026-10-19", timezone="Asia/Shanghai")
        db.add(plan)
        db.flush()
        db.add(
            DailyTask(
                user_id=uid, space_id=b, plan_id=plan.id, task_key="bad", action="REVIEW", concept_id="os"
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()


def test_cycle_keys_and_utc_usage_bucket_are_unique(client):
    from app.db.models import AnalysisDailyUsage

    register(client)
    uid = client.get("/api/v1/auth/me").json()["id"]
    with client.app.state.session_factory() as db:
        db.add_all([AnalysisDailyUsage(user_id=uid, utc_date="2026-10-19") for _ in range(2)])
        with pytest.raises(IntegrityError):
            db.flush()


def test_public_contract_rejects_internal_lease_and_credentials():
    from pydantic import ValidationError

    from app.schemas.activity import ActivityJobResponse

    value = dict(
        id="j",
        study_space_id="s",
        kind="daily_coordinate",
        status="queued",
        attempts=0,
        executions=0,
        available_at="2026-10-19T00:00:00Z",
        created_at="2026-10-19T00:00:00Z",
    )
    assert ActivityJobResponse(**value).id == "j"
    with pytest.raises(ValidationError):
        ActivityJobResponse(**value, lease_token="secret")
