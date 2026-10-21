from conftest import provider, register, space
from sqlalchemy import select


def chat_space(client):
    register(client)
    pid = provider(client)
    sid = space(client, pid)
    return f"/api/v1/study-spaces/{sid}"


def test_clear_request_applies_once_and_survives_restart(client, settings):
    from fastapi.testclient import TestClient

    from app.db.models import ChatTurn, PlanRevision
    from app.main import create_app

    root = chat_space(client)
    body = {"content": "每天15分钟，先学进程调度", "idempotency_key": "chat1"}
    r = client.post(root + "/chat/turns", json=body)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["outcome"] == "applied" and d["plan"]["daily_minutes"] == 15
    assert client.post(root + "/chat/turns", json=body).json() == d
    assert client.post(root + "/chat/turns", json={**body, "content": "different"}).status_code == 409
    with client.app.state.session_factory() as db:
        assert len(list(db.scalars(select(PlanRevision)))) == 1
        assert len(list(db.scalars(select(ChatTurn)))) == 1
    with TestClient(create_app(settings)) as other:
        other.post("/api/v1/auth/login", json={"username": "alice", "password": "strong-password-2026"})
        assert other.get(root + "/chat/turns").json()["items"][0]["id"] == d["id"]
        assert other.get(root + "/plan").json()["intent_version"] == 1


def test_reply_and_clarify_do_not_increment_intent(client):
    root = chat_space(client)
    for i, (message, outcome) in enumerate(
        [("为什么这样安排", "not_changed"), ("调整一下", "clarification_needed")]
    ):
        r = client.post(root + "/chat/turns", json={"content": message, "idempotency_key": f"chat{i}"})
        assert r.status_code == 201, r.text
        assert r.json()["outcome"] == outcome
    assert client.get(root + "/plan").json()["intent_version"] == 0
    assert client.get(root + "/plan/revisions").json()["items"] == []


def test_failed_business_validation_keeps_plan_and_audits_call_then_retry(client):
    from app.db.models import AgentRun
    from app.providers.fake import FakeAdapter

    root = chat_space(client)

    class BadPlan(FakeAdapter):
        async def generate_structured(self, messages, schema):
            if schema.get("title") == "ChatDecision":
                return {
                    "kind": "update_plan",
                    "reply": "建议",
                    "patch": {"daily_minutes": 15, "priority_concept_ids": ["absent"]},
                    "reason": "用户要求",
                }
            return await super().generate_structured(messages, schema)

    client.app.state.adapter_factory = lambda _: BadPlan()
    body = {"content": "每天15分钟", "idempotency_key": "retry-me"}
    failed = client.post(root + "/chat/turns", json=body).json()
    assert failed["status"] == "failed" and failed["retry_allowed"]
    assert client.get(root + "/plan").json()["daily_minutes"] == 30
    with client.app.state.session_factory() as db:
        runs = list(db.scalars(select(AgentRun).where(AgentRun.step == "planning_chat")))
        assert len(runs) == 1 and runs[0].error_code == "invalid_plan_change"
    client.app.state.adapter_factory = None
    assert client.post(root + "/chat/turns", json=body).json()["status"] == "failed"
    result = client.post(root + "/chat/turns", json={**body, "retry": True}).json()
    assert result["id"] == failed["id"] and result["outcome"] == "applied"


def test_new_nodes_preserve_existing_states_and_card_logs(client):
    from app.db.models import ReviewLogRecord, ReviewState

    root = chat_space(client)
    q = client.post(root + "/diagnostics").json()["items"][0]
    client.post(root + "/attempts", json={"item_id": q["id"], "answer": "A", "idempotency_key": "answer"})
    before = client.get(root + "/profile").json()["states"]
    with client.app.state.session_factory() as db:
        cards = {r.id: r.card for r in db.scalars(select(ReviewState))}
        logs = [r.log for r in db.scalars(select(ReviewLogRecord))]
    result = client.post(
        root + "/chat/turns", json={"content": "添加虚拟内存", "idempotency_key": "add-node"}
    )
    assert result.json()["outcome"] == "applied", result.text
    after = client.get(root + "/profile").json()["states"]
    assert [r for r in after if r["concept_id"] != "virtual_memory"] == before
    assert next(r for r in after if r["concept_id"] == "virtual_memory")["mastery_estimate"] is None
    with client.app.state.session_factory() as db:
        assert all(r.card == cards[r.id] for r in db.scalars(select(ReviewState)) if r.id in cards)
        assert [r.log for r in db.scalars(select(ReviewLogRecord))] == logs


def test_chat_history_and_cursor_are_owner_scoped(client):
    root = chat_space(client)
    for i in range(3):
        client.post(root + "/chat/turns", json={"content": "为什么", "idempotency_key": f"msg{i}"})
    page = client.get(root + "/chat/turns?limit=2").json()
    older = client.get(root + "/chat/turns", params={"limit": 2, "before": page["next_cursor"]}).json()
    assert len(page["items"]) == 2 and len(older["items"]) == 1
    assert not {r["id"] for r in page["items"]} & {r["id"] for r in older["items"]}
    assert client.get(root + "/chat/turns?before=invalid").status_code == 422
    client.post("/api/v1/auth/logout")
    register(client, "other")
    assert client.get(root + "/chat/turns").status_code == 404
    assert client.get(root + "/chat/turns/" + page["items"][0]["id"]).status_code == 404
