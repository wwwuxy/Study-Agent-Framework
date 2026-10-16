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
