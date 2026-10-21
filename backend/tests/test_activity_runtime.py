import asyncio
import time
from pathlib import Path

import pytest
from conftest import provider, register, space
from fastapi.testclient import TestClient
from sqlalchemy import select


def test_two_worker_ticks_publish_once_and_maintenance_blocks(client, settings):
    from app.activity.worker import tick
    from app.db.models import InboxMessage, PeriodicJob, WeeklySummary
    from app.providers.base import ProviderError

    register(client)
    sid = space(client, provider(client))
    root = f"/api/v1/study-spaces/{sid}"

    def forbidden(_):
        raise AssertionError("Background must never create a model adapter")

    client.app.state.adapter_factory = forbidden
    asyncio.run(tick(client.app))
    asyncio.run(tick(client.app))
    assert client.get(root + "/daily-plans/today").json()["plan"]
    with client.app.state.session_factory() as db:
        assert len(list(db.scalars(select(WeeklySummary)))) == 1
        assert len(list(db.scalars(select(InboxMessage)))) == 1
        assert len(list(db.scalars(select(PeriodicJob)))) == 2
    marker = Path(settings.material_storage_dir) / ".maintenance-lock"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("test-only")
    with pytest.raises(ProviderError, match="维护"):
        asyncio.run(tick(client.app))
    marker.unlink()
    asyncio.run(tick(client.app))
    assert client.get("/api/v1/analysis-usage").json()["calls"] == 0


def test_lifespan_starts_and_closes_worker_on_restart(client, settings):
    from app.main import create_app

    register(client)
    sid = space(client, provider(client))
    app = create_app(settings.model_copy(update={"m4_worker_enabled": True, "m4_tick_seconds": 1}))

    def forbidden(_):
        raise AssertionError("No background model calls")

    app.state.adapter_factory = forbidden
    with TestClient(app) as restarted:
        for _ in range(40):
            restarted.post(
                "/api/v1/auth/login", json={"username": "alice", "password": "strong-password-2026"}
            )
            if restarted.get(f"/api/v1/study-spaces/{sid}/daily-plans/today").json()["plan"]:
                break
            time.sleep(0.05)
        else:
            pytest.fail("No startup coordination")
        task = app.state.activity_worker_task
        assert not task.done()
        assert restarted.get("/health").json()["phase"] == "M4"
    assert task.done()
