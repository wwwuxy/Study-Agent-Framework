import json

import httpx
from conftest import provider, register, space


async def public_resolver(host, port):
    return ["93.184.216.34"]


def ready(client):
    register(client)
    pid = provider(client)
    sid = space(client, pid)
    root = f"/api/v1/study-spaces/{sid}"
    plan = client.post(root + "/daily-plans/refresh", json={"idempotency_key": "refresh"}).json()
    return root, plan["id"], pid


def test_manual_analysis_only_and_account_shared_quota(client):
    root, source, pid = ready(client)
    before = client.get(root + "/runs").json()
    assert client.get("/api/v1/analysis-usage").json()["calls"] == 0
    client.get(root + "/weekly-summaries/current")
    assert client.get(root + "/runs").json() == before
    body = {"source_kind": "daily_plan", "source_id": source, "idempotency_key": "analyze"}
    response = client.post(root + "/analyses", json=body)
    assert response.status_code == 201, response.text
    assert response.json()["content"]["summary"]
    assert response.json()["is_demo"]
    assert client.post(root + "/analyses", json=body).json() == response.json()
    assert client.get("/api/v1/analysis-usage").json()["calls"] == 1
    # Another space consumes the same account bucket.
    sid = space(client, pid, "second")
    other = f"/api/v1/study-spaces/{sid}"
    source2 = client.post(other + "/daily-plans/refresh", json={"idempotency_key": "refresh"}).json()["id"]
    client.app.state.settings.m4_analysis_daily_call_limit = 1
    assert (
        client.post(
            other + "/analyses", json={**body, "source_id": source2, "idempotency_key": "other"}
        ).status_code
        == 429
    )


def test_analysis_http_limit_one_request_and_unknown_usage_occupied(client):
    from app.providers.compatible import CompatibleAdapter

    root, source, _ = ready(client)
    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"summary": "建议先继续当前任务", "recommendations": [], "caveats": []}
                            )
                        }
                    }
                ]
            },
        )

    client.app.state.adapter_factory = lambda config: CompatibleAdapter(
        "https://example.com/v1",
        "test-key",
        "test",
        transport=httpx.MockTransport(respond),
        resolver=public_resolver,
    )
    response = client.post(
        root + "/analyses", json={"source_kind": "daily_plan", "source_id": source, "idempotency_key": "http"}
    )
    assert response.status_code == 201, response.text
    assert len(calls) == 1
    assert calls[0]["max_tokens"] == 1500
    assert response.json()["usage_status"] == "unknown"
    usage = client.get("/api/v1/analysis-usage").json()
    assert usage["occupied_tokens"] > 1500
    assert usage["unknown_calls"] == 1


def test_invalid_json_has_no_hidden_paid_retry_and_explicit_retry_is_new_attempt(client):
    from app.providers.compatible import CompatibleAdapter

    root, source, _ = ready(client)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "bad JSON"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10},
            },
        )

    client.app.state.adapter_factory = lambda config: CompatibleAdapter(
        "https://example.com/v1",
        "key",
        "m",
        transport=httpx.MockTransport(respond),
        resolver=public_resolver,
    )
    body = {"source_kind": "daily_plan", "source_id": source, "idempotency_key": "one"}
    failed = client.post(root + "/analyses", json=body).json()
    assert failed["status"] == "failed"
    assert len(calls) == 1
    client.post(root + "/analyses", json=body)
    assert len(calls) == 1
    result = client.post(
        root + "/analyses", json={**body, "idempotency_key": "retry", "retry_of": failed["id"]}
    )
    assert result.status_code == 201, result.text
    assert len(calls) == 2
    assert client.get("/api/v1/analysis-usage").json()["actual_tokens"] == 220


def test_analysis_source_id_is_scoped_and_quota_is_not_spent_on_invalid_source(client):
    root, source, _ = ready(client)
    assert (
        client.post(
            root + "/analyses",
            json={"source_kind": "weekly_summary", "source_id": source, "idempotency_key": "wrong"},
        ).status_code
        == 404
    )
    assert client.get("/api/v1/analysis-usage").json()["calls"] == 0
    client.post("/api/v1/auth/logout")
    register(client, "bob")
    assert (
        client.post(
            root + "/analyses",
            json={"source_kind": "daily_plan", "source_id": source, "idempotency_key": "one"},
        ).status_code
        == 404
    )


def test_account_analysis_history_is_paginated_and_private(client):
    from conftest import provider, register, space

    register(client)
    sid = space(client, provider(client))
    root = f"/api/v1/study-spaces/{sid}"
    plan = client.post(root + "/daily-plans/refresh", json={"idempotency_key": "day"}).json()
    for key in ("first", "second"):
        assert (
            client.post(
                root + "/analyses",
                json={"source_kind": "daily_plan", "source_id": plan["id"], "idempotency_key": key},
            ).status_code
            == 201
        )
    page = client.get("/api/v1/analyses?limit=1").json()
    assert len(page["items"]) == 1 and page["next_cursor"]
    next_page = client.get("/api/v1/analyses", params={"cursor": page["next_cursor"], "limit": 1}).json()
    assert next_page["items"][0]["id"] != page["items"][0]["id"]
    client.post("/api/v1/auth/logout")
    register(client, "bob")
    assert client.get("/api/v1/analyses").json()["items"] == []
