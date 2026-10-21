import asyncio
import os
import threading
import time

import httpx
import pytest
from sqlalchemy import event


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="requires real PostgreSQL row locks")
def test_material_job_lock_wait_does_not_block_asgi_answer_or_health(client, monkeypatch):
    from test_materials import configure, upload

    import app.core.orchestrator as orchestrator
    from app.jobs.materials import run_job
    from app.providers.fake_files import FakeFileAdapter

    _, sid = configure(client)
    root = f"/api/v1/study-spaces/{sid}"
    q = client.post(root + "/diagnostics").json()["items"][0]
    asset = upload(client, sid).json()
    original = orchestrator.compute_states
    cpu_started, cpu_release = threading.Event(), threading.Event()
    remote_started, remote_release = threading.Event(), threading.Event()

    def slow_cpu(*args):
        cpu_started.set()
        assert cpu_release.wait(3), "watchdog: CPU was not released"
        return original(*args)

    class ControlledFile(FakeFileAdapter):
        async def upload_file(self, content, filename):
            remote_started.set()
            assert await asyncio.to_thread(remote_release.wait, 3)
            return await super().upload_file(content, filename)

    monkeypatch.setattr(orchestrator, "compute_states", slow_cpu)
    client.app.state.adapter_factory = lambda _: ControlledFile()
    # Bound RED failure: synchronous lock waiting times out rather than hanging the suite.
    engine = client.app.state.engine
    engine.dispose()

    @event.listens_for(engine, "connect")
    def bounded_wait(connection, _):
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout='350ms'")
        connection.commit()

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app),
            base_url="http://testserver",
            cookies=dict(client.cookies),
        ) as http:
            job = asyncio.create_task(run_job(client.app, asset["job_id"]))
            assert await asyncio.to_thread(remote_started.wait, 3)
            answer = asyncio.create_task(
                http.post(
                    root + "/attempts",
                    json={"item_id": q["id"], "answer": "A", "idempotency_key": "concurrent-answer"},
                )
            )
            assert await asyncio.to_thread(cpu_started.wait, 3), (
                answer.result().text if answer.done() else "answer waiting"
            )
            start = time.monotonic()
            remote_release.set()
            try:
                await asyncio.sleep(0.08)
                health = await http.get("/health")
                assert health.status_code == 200
                assert time.monotonic() - start < 0.25, (
                    "worker blocked the ASGI event loop waiting for the answer lock"
                )
            finally:
                cpu_release.set()
                response = await answer
                await job
            assert response.status_code == 201, response.text
            assert (await http.get(f"/api/v1/jobs/{asset['job_id']}")).json()["status"] == "succeeded"

    asyncio.run(scenario())
