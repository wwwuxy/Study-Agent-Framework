import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.settings import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    pg_url = os.environ.get("TEST_DATABASE_URL")
    admin = None
    schema = "test_" + uuid.uuid4().hex
    url = f"sqlite:///{tmp_path}/test.db"
    if pg_url:
        admin = create_engine(pg_url)
        with admin.begin() as db:
            db.execute(text(f"CREATE SCHEMA {schema}"))
        url = (
            make_url(pg_url)
            .update_query_dict({"options": "-csearch_path=" + schema})
            .render_as_string(hide_password=False)
        )
    yield Settings(
        database_url=url,
        credential_encryption_key=Fernet.generate_key().decode(),
        enable_fake_provider=True,
        cookie_secure=False,
        material_storage_dir=str(tmp_path / "materials"),
        material_worker_enabled=False,
        exam_worker_enabled=False,
        m4_worker_enabled=False,
    )
    if admin:
        with admin.begin() as db:
            db.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


@pytest.fixture
def client(settings, monkeypatch):
    app = create_app(settings)
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
    with TestClient(app) as client:
        yield client
    app.state.engine.dispose()


def register(client, name="alice"):
    response = client.post(
        "/api/v1/auth/register", json={"username": name, "password": "strong-password-2026"}
    )
    assert response.status_code == 201, response.text


def provider(client):
    response = client.post(
        "/api/v1/providers",
        json={
            "name": "离线演示",
            "provider_type": "fake",
            "chat_model": "demo-model",
            "api_key": "demo-secret",
        },
    )
    assert response.status_code == 201, response.text
    key = response.json()["id"]
    assert client.post(f"/api/v1/providers/{key}/test").status_code == 200
    return key


def space(client, provider_id, key="space-1"):
    response = client.post(
        "/api/v1/study-spaces",
        json={
            "provider_id": provider_id,
            "goal": "学习操作系统",
            "idempotency_key": key,
            "daily_minutes": 30,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]
