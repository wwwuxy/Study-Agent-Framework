from conftest import provider, register, space
from sqlalchemy import select

from app.db.models import AssessmentItem
from app.providers.base import ProviderError
from app.providers.fake import FakeAdapter


def test_unverified_provider_cannot_create_space_and_validation_never_echoes_secrets(client):
    register(client)
    config = client.post(
        "/api/v1/providers",
        json={"name": "demo", "provider_type": "fake", "chat_model": "demo", "api_key": "secret"},
    ).json()
    response = client.post(
        "/api/v1/study-spaces",
        json={"provider_id": config["id"], "goal": "学习系统", "idempotency_key": "one"},
    )
    assert response.status_code == 422
    response = client.post(
        "/api/v1/providers",
        json={
            "name": "",
            "provider_type": "fake",
            "chat_model": "demo",
            "api_key": "NEVER_ECHO_THIS",
            "bad": "PRIVATE",
        },
    )
    assert response.status_code == 422
    assert "NEVER_ECHO_THIS" not in response.text
    assert "PRIVATE" not in response.text


def test_failed_provider_retest_invalidates_previous_success(client):
    register(client)
    pid = provider(client)

    class InvalidKey(FakeAdapter):
        async def probe_capabilities(self):
            raise ProviderError("invalid_api_key", "密钥无效", 422)

    client.app.state.adapter_factory = lambda _: InvalidKey()
    assert client.post(f"/api/v1/providers/{pid}/test").status_code == 422
    assert client.get(f"/api/v1/providers/{pid}/capabilities").json()["tested"] is False
    assert (
        client.post(
            "/api/v1/study-spaces", json={"provider_id": pid, "goal": "新学习", "idempotency_key": "one"}
        ).status_code
        == 422
    )


def test_generated_question_mapping_is_validated_before_persisting(client):
    register(client)
    sid = space(client, provider(client))

    class WrongMapping(FakeAdapter):
        async def generate_structured(self, messages, schema):
            result = await super().generate_structured(messages, schema)
            for item in result["items"]:
                item["concept_keys"] = ["other_space_concept"]
            return result

    client.app.state.adapter_factory = lambda _: WrongMapping()
    response = client.post(f"/api/v1/study-spaces/{sid}/diagnostics")
    assert response.status_code == 502
    with client.app.state.session_factory() as db:
        assert db.scalars(select(AssessmentItem).where(AssessmentItem.space_id == sid)).all() == []


def test_fake_provider_is_not_a_fallback_when_disabled(client):
    register(client)
    client.app.state.settings.enable_fake_provider = False
    response = client.post(
        "/api/v1/providers",
        json={"name": "demo", "provider_type": "fake", "chat_model": "demo", "api_key": "demo"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "demo_disabled"


def test_credential_update_requires_reprobe_without_losing_progress(client):
    register(client)
    pid = provider(client)
    sid = space(client, pid)
    before = client.get(f"/api/v1/study-spaces/{sid}/profile").json()
    assert client.patch(f"/api/v1/providers/{pid}", json={"api_key": "new-secret"}).status_code == 200
    assert client.get(f"/api/v1/providers/{pid}/capabilities").json()["tested"] is False
    assert client.get(f"/api/v1/study-spaces/{sid}/profile").json() == before
    assert client.delete(f"/api/v1/providers/{pid}").status_code == 409


def test_concurrent_duplicate_submissions_have_one_evidence_event(client):
    from concurrent.futures import ThreadPoolExecutor

    register(client)
    sid = space(client, provider(client))
    root = f"/api/v1/study-spaces/{sid}"
    item = client.post(root + "/diagnostics").json()["items"][0]
    body = {"item_id": item["id"], "answer": "A", "idempotency_key": "concurrent"}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: client.post(root + "/attempts", json=body), range(4)))
    assert all(result.status_code == 201 for result in results)
    assert len({result.json()["event_id"] for result in results}) == 1
    events = client.get(root + "/events").json()
    assert sum(e["type"] == "diagnostic_submitted" for e in events) == 1


def test_lowercase_option_keys_are_answerable_without_collapsing_distinct_keys(client):
    register(client)
    sid = space(client, provider(client))

    class LowercaseOptions(FakeAdapter):
        async def generate_structured(self, messages, schema):
            result = await super().generate_structured(messages, schema)
            for item in result["items"]:
                item["options"] = {"a": "正确选项", "A": "错误选项"}
                item["answer"] = "a"
            return result

    client.app.state.adapter_factory = lambda _: LowercaseOptions()
    root = f"/api/v1/study-spaces/{sid}"
    items = client.post(root + "/diagnostics").json()["items"]
    correct = client.post(
        root + "/attempts", json={"item_id": items[0]["id"], "answer": "a", "idempotency_key": "lower"}
    )
    assert correct.status_code == 201
    assert correct.json()["is_correct"] is True
    wrong = client.post(
        root + "/attempts", json={"item_id": items[1]["id"], "answer": "A", "idempotency_key": "upper"}
    )
    assert wrong.status_code == 201
    assert wrong.json()["is_correct"] is False


def test_old_probe_cannot_enable_a_changed_configuration(client):
    from app.db.models import ProviderConfig

    register(client)
    pid = provider(client)

    class ConcurrentEdit(FakeAdapter):
        async def probe_capabilities(self):
            with client.app.state.session_factory() as other:
                config = other.get(ProviderConfig, pid)
                config.chat_model = "changed-during-probe"
                config.tested = False
                config.capabilities = {}
                other.commit()
            return await super().probe_capabilities()

    client.app.state.adapter_factory = lambda _: ConcurrentEdit()
    response = client.post(f"/api/v1/providers/{pid}/test")
    assert response.status_code == 409
    assert client.get(f"/api/v1/providers/{pid}/capabilities").json()["tested"] is False


def test_request_log_has_trace_id_without_sensitive_body(client, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="uvicorn.error.study_agent")
    response = client.post(
        "/api/v1/auth/register", json={"username": "loguser", "password": "DO_NOT_LOG_PASSWORD"}
    )
    assert response.status_code == 201
    assert response.headers["x-request-id"] in caplog.text
    assert "DO_NOT_LOG_PASSWORD" not in caplog.text
