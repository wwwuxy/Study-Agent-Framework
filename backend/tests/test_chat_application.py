import pytest
from conftest import provider, register, space
from sqlalchemy import select


def setup(client):
    register(client)
    sid = space(client, provider(client))
    return sid


def test_budget_and_priority_change_real_next_action(client):
    from app.chat.application import apply_decision
    from app.db.models import ChatTurn, PlanRevision, ReviewState, StudySpace
    from app.schemas.chat import ChatDecision

    sid = setup(client)
    with client.app.state.session_factory() as db:
        s = db.get(StudySpace, sid)
        before = [r.card for r in db.scalars(select(ReviewState))]
        t = ChatTurn(user_id=s.user_id, space_id=sid, request_key="one", request_digest="x", content="15分钟")
        db.add(t)
        db.flush()
        r = apply_decision(
            db,
            s,
            t,
            ChatDecision(
                kind="update_plan",
                reply="建议调整",
                patch={"daily_minutes": 15, "priority_concept_ids": ["process"]},
                reason="用户要求",
            ),
        )
        assert r.after["daily_minutes"] == 15 and r.plan["intent_version"] == 1
        assert r.plan["next_action"]["concept_ids"] == ["os"]
        assert [r.card for r in db.scalars(select(ReviewState))] == before
        assert len(list(db.scalars(select(PlanRevision)))) == 1


def test_bad_graph_or_scope_rolls_back_every_change(client):
    from app.chat.application import apply_decision
    from app.db.models import ChatTurn, StudySpace
    from app.providers.base import ProviderError
    from app.schemas.chat import ChatDecision

    sid = setup(client)
    with client.app.state.session_factory() as db:
        s = db.get(StudySpace, sid)
        t = ChatTurn(user_id=s.user_id, space_id=sid, request_key="one", request_digest="x", content="bad")
        db.add(t)
        db.flush()
        with pytest.raises(ProviderError):
            apply_decision(
                db,
                s,
                t,
                ChatDecision(
                    kind="update_plan",
                    reply="bad",
                    patch={"daily_minutes": 15, "priority_concept_ids": ["unknown"]},
                    reason="bad",
                ),
            )
        db.rollback()
    assert client.get(f"/api/v1/study-spaces/{sid}").json()["daily_minutes"] == 30


def test_necessary_prerequisite_lesson_is_not_paused(client):
    sid = setup(client)
    root = f"/api/v1/study-spaces/{sid}"
    lesson = client.post(root + "/lessons", json={"idempotency_key": "lesson"}).json()
    result = client.post(root + "/chat/turns", json={"content": "先学进程调度", "idempotency_key": "focus"})
    assert result.json()["outcome"] == "applied"
    current = client.get(root + "/lessons/current").json()
    assert current and current["id"] == lesson["id"]
    assert client.get(root + "/lessons/paused").json() == []
