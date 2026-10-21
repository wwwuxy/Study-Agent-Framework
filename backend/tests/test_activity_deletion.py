from datetime import timedelta

import pytest
from conftest import provider, register, space
from sqlalchemy import select

from app.db import models as m


def test_deletion_erases_all_activity_retains_quota_and_fences_late_results(client):
    from app.activity.analysis import prepare_analysis, publish_analysis
    from app.activity.calendar import previous_week
    from app.activity.queue import claim_job, finish_job
    from app.activity.scheduler import enqueue_cycles
    from app.activity.weekly import publish_week
    from app.chat.contracts import ModelCallResult
    from app.core.security import token_hash
    from app.providers.base import ProviderError
    from app.schemas.analyses import AnalysisContent, AnalysisRequest

    register(client)
    pid = provider(client)
    sid = space(client, pid)
    root = f"/api/v1/study-spaces/{sid}"
    plan = client.post(root + "/daily-plans/refresh", json={"idempotency_key": "day"}).json()
    uid = client.get("/api/v1/auth/me").json()["id"]
    factory, now = client.app.state.session_factory, m.utcnow()
    publish_week(factory, uid, sid, previous_week(now, "Asia/Shanghai"), now)
    enqueue_cycles(factory, now)
    claim = claim_job(factory, now)
    body = AnalysisRequest(source_kind="daily_plan", source_id=plan["id"], idempotency_key="ai")
    prepared = prepare_analysis(
        factory, token_hash(client.cookies["study_session"]), sid, body, now, client.app.state.settings
    )
    before = client.get("/api/v1/analysis-usage").json()
    removed = client.delete(root)
    assert removed.status_code == 200, removed.text
    for model in (
        m.DailyTask,
        m.DailyPlan,
        m.LearningSuggestion,
        m.InboxMessage,
        m.WeeklySummary,
        m.AnalysisRun,
        m.PeriodicJob,
    ):
        with factory() as db:
            assert not list(db.scalars(select(model).where(model.space_id == sid))), model
    call = ModelCallResult(AnalysisContent(summary="late"), 1, {"input_tokens": 1, "output_tokens": 1})
    with pytest.raises(ProviderError, match="移除"):
        publish_analysis(factory, prepared, call, now + timedelta(seconds=1))
    assert not finish_job(factory, claim, now)
    assert enqueue_cycles(factory, now) == 0
    assert client.get("/api/v1/analysis-usage").json() == before


def test_provider_required_by_inflight_analysis_cannot_be_deleted_after_switch(client):
    from app.activity.analysis import prepare_analysis
    from app.core.security import token_hash
    from app.schemas.analyses import AnalysisRequest

    register(client)
    pid = provider(client)
    sid = space(client, pid)
    root = f"/api/v1/study-spaces/{sid}"
    plan = client.post(root + "/daily-plans/refresh", json={"idempotency_key": "day"}).json()
    prepare_analysis(
        client.app.state.session_factory,
        token_hash(client.cookies["study_session"]),
        sid,
        AnalysisRequest(source_kind="daily_plan", source_id=plan["id"], idempotency_key="ai"),
        m.utcnow(),
        client.app.state.settings,
    )
    next_pid = provider(client)
    assert client.patch(root, json={"provider_id": next_pid}).status_code == 200
    result = client.delete(f"/api/v1/providers/{pid}")
    assert result.status_code == 409, result.text
    assert result.json()["error"]["code"] == "provider_in_use"
