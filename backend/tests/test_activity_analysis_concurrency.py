import asyncio
import threading

import httpx
from conftest import provider, register, space


def test_analysis_wait_allows_health_quota_blocks_second_call_and_logout_cancels(client):
    from app.providers.fake import FakeAdapter

    register(client)
    sid = space(client, provider(client))
    root = f"/api/v1/study-spaces/{sid}"
    plan = client.post(root + "/daily-plans/refresh", json={"idempotency_key": "plan"}).json()["id"]
    started, release = threading.Event(), threading.Event()

    class Controlled(FakeAdapter):
        async def generate_structured(self, messages, schema):
            if schema["title"] == "AnalysisContent":
                self.usage["usage_reported"] = False
                started.set()
                assert await asyncio.to_thread(release.wait, 5)
            return await super().generate_structured(messages, schema)

    client.app.state.adapter_factory = lambda _: Controlled()
    client.app.state.settings.m4_analysis_daily_call_limit = 1

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app),
            base_url="http://testserver",
            cookies=dict(client.cookies),
        ) as http:
            body = {"source_kind": "daily_plan", "source_id": plan, "idempotency_key": "first"}
            running = asyncio.create_task(http.post(root + "/analyses", json=body))
            assert await asyncio.to_thread(started.wait, 3)
            try:
                assert (await asyncio.wait_for(http.get("/health"), 1)).status_code == 200
                assert (
                    await asyncio.wait_for(
                        http.post(root + "/analyses", json={**body, "idempotency_key": "second"}), 1
                    )
                ).status_code == 429
                assert (await http.post("/api/v1/auth/logout")).status_code == 204
            finally:
                release.set()
            result = await running
            assert result.json()["status"] == "cancelled"
            assert result.json()["content"] is None

    asyncio.run(scenario())
    client.post("/api/v1/auth/login", json={"username": "alice", "password": "strong-password-2026"})
    usage = client.get("/api/v1/analysis-usage").json()
    assert usage["calls"] == 1 and usage["occupied_tokens"] > 0 and usage["unknown_calls"] == 1


def test_postgres_parallel_spaces_share_one_quota_reservation(client, settings):
    import concurrent.futures

    import pytest

    from app.activity.analysis import prepare_analysis
    from app.core.security import token_hash
    from app.db.models import utcnow
    from app.providers.base import ProviderError
    from app.schemas.analyses import AnalysisRequest

    if not settings.database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL row-lock concurrency")
    register(client)
    pid = provider(client)
    spaces = [space(client, pid, key="s" + str(n)) for n in range(2)]
    plans = [
        client.post(f"/api/v1/study-spaces/{sid}/daily-plans/refresh", json={"idempotency_key": "p"}).json()[
            "id"
        ]
        for sid in spaces
    ]
    settings.m4_analysis_daily_call_limit = 1
    token = token_hash(client.cookies["study_session"])
    barrier = threading.Barrier(2)

    def prepare(n):
        barrier.wait(timeout=3)
        try:
            return prepare_analysis(
                client.app.state.session_factory,
                token,
                spaces[n],
                AnalysisRequest(source_kind="daily_plan", source_id=plans[n], idempotency_key="same"),
                utcnow(),
                settings,
            )
        except ProviderError as exc:
            return exc.status

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(prepare, range(2)))
    assert sum(value == 429 for value in results) == 1
    assert client.get("/api/v1/analysis-usage").json()["calls"] == 1
