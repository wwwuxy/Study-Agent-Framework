from conftest import provider, register, space
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.db.models import LearningEvent, ProviderConfig
from app.main import create_app
from app.providers.base import ProviderError
from app.providers.fake import FakeAdapter


def test_full_learning_loop_persistence_and_model_switch(client, settings):
    register(client)
    pid = provider(client)
    sid = space(client, pid)
    base = f"/api/v1/study-spaces/{sid}"
    assert client.get(base + "/concepts").json()[0]["source_status"] == "model_generated_unverified"
    assert all(s["status"] == "unknown" for s in client.get(base + "/profile").json()["states"])
    diagnosis = client.post(base + "/diagnostics").json()
    assert 5 <= len(diagnosis["items"]) <= 10
    assert "answer" not in diagnosis["items"][0]
    assert client.post(base + "/diagnostics").json() == diagnosis
    for index, item in enumerate(diagnosis["items"]):
        response = client.post(
            base + "/attempts",
            json={
                "item_id": item["id"],
                "answer": "B" if index == 0 else "A",
                "idempotency_key": f"diag-{index}",
            },
        )
        assert response.status_code == 201, response.text
    action = client.get(base + "/next-action").json()
    assert action["reason"] and action["evidence_event_ids"]
    lesson = client.post(base + "/lessons", json={"idempotency_key": "lesson-1"}).json()
    assert lesson["explanation"] and lesson["exercises"]
    before = client.get(base + "/profile").json()
    completed = client.post(base + f"/lessons/{lesson['id']}/complete", json={"idempotency_key": "view-1"})
    assert completed.status_code == 200
    assert client.get(base + "/profile").json() == before
    item = lesson["exercises"][0]
    body = {"item_id": item["id"], "answer": "A", "idempotency_key": "practice-1"}
    result = client.post(base + "/attempts", json=body)
    assert result.status_code == 201, result.text
    assert client.post(base + "/attempts", json=body).json() == result.json()
    assert client.post(base + "/attempts", json={**body, "answer": "B"}).status_code == 409
    assert client.post(base + "/attempts", json={**body, "idempotency_key": "farm"}).status_code == 409
    expected_profile = client.get(base + "/profile").json()
    assert client.post(base + "/profile/rebuild").json() == expected_profile
    expected_events = client.get(base + "/events").json()
    second = provider(client)
    assert client.patch(base, json={"provider_id": second}).status_code == 200
    assert client.delete(f"/api/v1/providers/{pid}").status_code == 204
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get(base).status_code == 401
    restarted = create_app(settings)
    with TestClient(restarted) as other:
        assert (
            other.post(
                "/api/v1/auth/login", json={"username": "alice", "password": "strong-password-2026"}
            ).status_code
            == 200
        )
        assert other.get(base + "/profile").json() == expected_profile
        assert other.get(base + "/events").json() == expected_events
        assert other.get(base + "/plan").json()["next_action"]["reason"]
    restarted.state.engine.dispose()


def test_hint_cannot_be_hidden_by_client(client):
    register(client)
    sid = space(client, provider(client))
    base = f"/api/v1/study-spaces/{sid}"
    item = client.post(base + "/diagnostics").json()["items"][0]
    assert (
        client.post(base + f"/items/{item['id']}/hint", json={"idempotency_key": "hint-1"}).status_code == 200
    )
    response = client.post(
        base + "/attempts", json={"item_id": item["id"], "answer": "A", "idempotency_key": "answer"}
    )
    assert response.json()["assistance_level"] == "hint"
    state = next(
        s
        for s in client.get(base + "/profile").json()["states"]
        if s["concept_id"] == item["concept_keys"][0]
    )
    assert state["independent_correct_count"] == 0


def test_user_isolation_credentials_and_csrf(client):
    register(client)
    pid = provider(client)
    sid = space(client, pid)
    assert "demo-secret" not in client.get("/api/v1/providers").text
    with client.app.state.session_factory() as db:
        stored = db.get(ProviderConfig, pid).encrypted_api_key
        assert "demo-secret" not in stored
    assert client.post("/api/v1/auth/logout").status_code == 204
    register(client, "bob")
    for suffix in ["", "/concepts", "/profile", "/events", "/plan", "/next-action", "/runs"]:
        assert client.get(f"/api/v1/study-spaces/{sid}{suffix}").status_code == 404
    assert client.post(f"/api/v1/study-spaces/{sid}/diagnostics").status_code == 404
    assert client.post(f"/api/v1/providers/{pid}/test").status_code == 404
    assert client.get(f"/api/v1/providers/{pid}/capabilities").status_code == 404
    assert client.get("/api/v1/study-spaces").json() == []
    response = client.post("/api/v1/providers", headers={"Origin": "https://attacker.example"}, json={})
    assert response.status_code == 403


def test_initialization_idempotent_and_invalid_schema_rolls_back(client):
    register(client)
    pid = provider(client)
    sid = space(client, pid)
    assert space(client, pid) == sid

    class Broken(FakeAdapter):
        async def generate_structured(self, messages, schema):
            return {"concepts": []}

    client.app.state.adapter_factory = lambda config: Broken()
    response = client.post(
        "/api/v1/study-spaces", json={"provider_id": pid, "goal": "新目标", "idempotency_key": "broken"}
    )
    assert response.status_code == 502
    assert len(client.get("/api/v1/study-spaces").json()) == 1


def test_provider_failure_does_not_modify_existing_learning_state(client):
    register(client)
    pid = provider(client)
    sid = space(client, pid)

    class Timeout(FakeAdapter):
        async def generate_structured(self, messages, schema):
            raise ProviderError("provider_timeout", "模型请求超时")

    base = f"/api/v1/study-spaces/{sid}"
    before = client.get(base + "/profile").json()
    client.app.state.adapter_factory = lambda config: Timeout()
    assert client.post(base + "/diagnostics").json()["error"]["code"] == "provider_timeout"
    assert client.get(base + "/profile").json() == before
    assert client.get(base + "/events").json() == []


def test_events_are_append_only_at_database_level(client):
    register(client)
    sid = space(client, provider(client))
    base = f"/api/v1/study-spaces/{sid}"
    item = client.post(base + "/diagnostics").json()["items"][0]
    client.post(base + "/attempts", json={"item_id": item["id"], "answer": "A", "idempotency_key": "one"})
    with client.app.state.session_factory() as db:
        import pytest

        with pytest.raises(Exception, match="append.only"):
            db.execute(text("UPDATE learning_events SET type='lesson_viewed'"))
            db.commit()
        db.rollback()
        assert len(db.scalars(select(LearningEvent)).all()) >= 1
