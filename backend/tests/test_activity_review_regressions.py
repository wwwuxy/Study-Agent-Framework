"""Regressions from the single independent M4 review (all isolated data)."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from conftest import provider, register, space
from sqlalchemy import select


def setup(client):
    register(client)
    sid = space(client, provider(client))
    return sid, client.get("/api/v1/auth/me").json()["id"], client.app.state.session_factory


@pytest.mark.parametrize("kind", ["daily_plan", "weekly_summary"])
def test_live_intent_change_fences_analysis_of_unchanged_source(client, kind):
    from app.activity.analysis import prepare_analysis, publish_analysis
    from app.chat.contracts import ModelCallResult
    from app.core.security import token_hash
    from app.db.models import StudySpace, utcnow
    from app.schemas.analyses import AnalysisContent, AnalysisRequest

    sid, uid, factory = setup(client)
    root = f"/api/v1/study-spaces/{sid}"
    suffix = "/daily-plans/refresh" if kind == "daily_plan" else "/weekly-summaries/refresh"
    source = client.post(root + suffix, json={"idempotency_key": "source"}).json()["id"]
    prepared = prepare_analysis(
        factory,
        token_hash(client.cookies["study_session"]),
        sid,
        AnalysisRequest(source_kind=kind, source_id=source, idempotency_key="analysis"),
        utcnow(),
        client.app.state.settings,
    )
    with factory.begin() as db:
        db.get(StudySpace, sid).daily_minutes = 15
    result = publish_analysis(
        factory,
        prepared,
        ModelCallResult(
            AnalysisContent(summary="old context"),
            1,
            {"usage_reported": True, "prompt_tokens": 4, "completion_tokens": 2},
        ),
        utcnow(),
    )
    assert result.status == "conflict" and result.content is None
    assert client.get("/api/v1/analysis-usage").json()["actual_tokens"] == 6


def test_completed_carryover_retains_today_allocation_and_spent_budget(client):
    from app.activity.daily import coordinate_day
    from app.db.models import utcnow

    sid, uid, factory = setup(client)
    now = utcnow()
    old = coordinate_day(factory, uid, sid, now - timedelta(days=1))
    tid = old.slots[0].task.id
    root = f"/api/v1/study-spaces/{sid}"
    receipt = client.post(root + f"/tasks/{tid}/start", json={"idempotency_key": "start"}).json()
    today = coordinate_day(factory, uid, sid, now)
    assert today.slots[0].carried_over
    for n, item in enumerate(receipt["item_ids"]):
        assert (
            client.post(
                root + "/attempts", json={"item_id": item, "answer": "A", "idempotency_key": f"a{n}"}
            ).status_code
            == 201
        )
    assert client.post(root + f"/tasks/{tid}/complete", json={"idempotency_key": "done"}).status_code == 200
    today = coordinate_day(factory, uid, sid, now)
    assert any(s.task.id == tid and s.task.status == "completed" for s in today.slots)
    assert sum(s.allocated_minutes for s in today.slots) <= today.budget_minutes
    assert (
        sum(s.allocated_minutes for s in today.slots if s.task.id != tid)
        <= today.budget_minutes - old.slots[0].allocated_minutes
    )


def test_completed_successor_resolves_historical_postponed_backlog(client):
    from app.activity.calendar import local_day
    from app.activity.daily import coordinate_day
    from app.activity.snapshot import read_snapshot
    from app.activity.suggestions import derive_suggestions
    from app.db.models import DailyTask, StudySpace, utcnow

    sid, uid, factory = setup(client)
    now = utcnow()
    for offset in (3, 2, 1):
        day = now - timedelta(days=offset)
        plan = coordinate_day(factory, uid, sid, day)
        with factory.begin() as db:
            for task in db.scalars(select(DailyTask).where(DailyTask.plan_id == plan.id)):
                task.created_at = day
    current = coordinate_day(factory, uid, sid, now)
    tid = current.slots[0].task.id
    root = f"/api/v1/study-spaces/{sid}"
    receipt = client.post(root + f"/tasks/{tid}/start", json={"idempotency_key": "start"}).json()
    for n, item in enumerate(receipt["item_ids"]):
        assert (
            client.post(
                root + "/attempts", json={"item_id": item, "answer": "A", "idempotency_key": f"a{n}"}
            ).status_code
            == 201
        )
    coordinate_day(factory, uid, sid, now)
    with factory() as db:
        snapshot = read_snapshot(db, db.get(StudySpace, sid), now)
    assert not any(
        s["kind"] == "overload" for s in derive_suggestions(snapshot, local_day(now, "Asia/Shanghai"))
    )


def snapshot_at(client, now):
    from app.activity.snapshot import read_snapshot
    from app.db.models import StudySpace

    sid, uid, factory = setup(client)
    with factory() as db:
        return read_snapshot(db, db.get(StudySpace, sid), now)


def test_skip_is_counted_in_disposition_week_only(client):
    from app.activity.calendar import current_week, previous_week
    from app.activity.weekly import summarize_week

    now = datetime(2026, 10, 19, 12, tzinfo=UTC)
    snapshot = snapshot_at(client, now)
    snapshot = replace(
        snapshot,
        tasks=(
            {
                "status": "skipped",
                "created_at": (now - timedelta(days=1)).isoformat(),
                "disposed_at": (now - timedelta(minutes=1)).isoformat(),
            },
        ),
    )
    assert summarize_week(snapshot, current_week(now, "UTC")).skipped_tasks == 1
    assert summarize_week(snapshot, previous_week(now, "UTC")).skipped_tasks == 0


def test_cross_week_completion_is_visible_in_completion_week(client):
    from app.activity.calendar import current_week, previous_week
    from app.activity.weekly import summarize_week

    now = datetime(2026, 10, 19, 12, tzinfo=UTC)
    snapshot = snapshot_at(client, now)
    snapshot = replace(
        snapshot,
        tasks=(
            {
                "status": "completed",
                "created_at": (now - timedelta(days=1)).isoformat(),
                "started_at": (now - timedelta(days=1)).isoformat(),
                "completed_at": (now - timedelta(minutes=1)).isoformat(),
            },
        ),
    )
    current = summarize_week(snapshot, current_week(now, "UTC"))
    assert current.task_completion.numerator == 1 and current.task_completion.denominator == 1
    assert summarize_week(snapshot, previous_week(now, "UTC")).task_completion.numerator == 0


def test_current_preview_keeps_four_closed_weeks_including_stagnation(client, monkeypatch):
    from app.activity.calendar import current_week
    from app.activity.weekly import forecast_snapshot

    now = datetime(2026, 10, 19, 12, tzinfo=UTC)
    snapshot = snapshot_at(client, now)
    snapshot = replace(
        snapshot,
        concepts=tuple({"key": str(n), "prerequisites": []} for n in range(8)),
        events=({"type": "assessment_submitted", "occurred_at": (now - timedelta(days=35)).isoformat()},),
    )
    oldest = datetime(2026, 9, 21, tzinfo=UTC)
    monkeypatch.setattr(
        "app.activity.weekly.count_mastered", lambda snapshot, at: max(0, (at - oldest).days // 7 - 1)
    )
    estimate = forecast_snapshot(snapshot, current_week(now, "UTC"))
    assert estimate.weekly_gains == [0, 1, 1, 1]
    assert estimate.status == "insufficient_data"


def test_undated_legacy_skip_does_not_invent_week_or_crash(client):
    from app.activity.calendar import current_week
    from app.activity.weekly import summarize_week

    now = datetime(2026, 10, 19, 12, tzinfo=UTC)
    snapshot = replace(
        snapshot_at(client, now), tasks=({"status": "skipped", "created_at": now.isoformat()},)
    )
    assert summarize_week(snapshot, current_week(now, "UTC")).skipped_tasks == 0
