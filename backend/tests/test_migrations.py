from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_migration_upgrade_append_only_guards_and_downgrade(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/migration.db"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(url)
    assert {"learning_events", "learner_concept_states", "assessment_items", "concept_prerequisites"} <= set(
        inspect(engine).get_table_names()
    )
    with engine.begin() as db:
        # A trigger must fire even if no rows match: row-level SQLite triggers require a real row.
        db.execute(
            text(
                "INSERT INTO learning_events (id,user_id,space_id,type,idempotency_key,data,occurred_at) "
                "VALUES ('evt','u','s','lesson_viewed','k','{}','2026-10-15')"
            )
        )
    for operation in [
        "UPDATE learning_events SET type='assessment_submitted'",
        "DELETE FROM learning_events",
    ]:
        with pytest.raises(Exception, match="append.only"):
            with engine.begin() as db:
                db.execute(text(operation))
    command.downgrade(config, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]
    command.upgrade(config, "head")
    engine.dispose()


def test_m2_migration_preserves_existing_m1_space_and_default_consent(tmp_path, monkeypatch):
    from sqlalchemy import MetaData

    from app.db.models import utcnow

    url = f"sqlite:///{tmp_path}/existing.db"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "0001")
    engine = create_engine(url)
    metadata = MetaData()
    metadata.reflect(engine)
    with engine.begin() as db:
        db.execute(
            metadata.tables["users"].insert(),
            {
                "id": "u",
                "username": "old-user",
                "password_hash": "test-hash",
                "timezone": "Asia/Shanghai",
                "created_at": utcnow(),
            },
        )
        db.execute(
            metadata.tables["provider_configs"].insert(),
            {
                "id": "p",
                "user_id": "u",
                "name": "old",
                "provider_type": "fake",
                "base_url": "https://example.com/v1",
                "chat_model": "demo",
                "encrypted_api_key": "test",
                "timeout_seconds": 30,
                "tested": True,
                "capabilities": {},
                "created_at": utcnow(),
            },
        )
        db.execute(
            metadata.tables["study_spaces"].insert(),
            {
                "id": "s",
                "user_id": "u",
                "provider_id": "p",
                "goal": "old goal",
                "daily_minutes": 30,
                "expected_level": "基础",
                "status": "ready",
                "init_key": "old",
                "request_digest": "old",
                "created_at": utcnow(),
            },
        )
    command.upgrade(config, "head")
    with engine.connect() as db:
        assert db.execute(text("SELECT goal, allow_general_knowledge FROM study_spaces")).one() == (
            "old goal",
            0,
        )
        assert db.execute(text("SELECT embedding_model FROM provider_configs")).scalar() is None
    command.check(config)
    command.downgrade(config, "0001")
    command.upgrade(config, "head")
    with engine.connect() as db:
        assert db.execute(text("SELECT goal FROM study_spaces")).scalar() == "old goal"
    engine.dispose()
