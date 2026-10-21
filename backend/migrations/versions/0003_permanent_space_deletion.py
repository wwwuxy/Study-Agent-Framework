"""Permanent space deletion with scrubbed cleanup tombstones.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def set_event_guard(permanent):
    if op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER learning_events_no_delete")
        condition = (
            "WHEN NOT EXISTS (SELECT 1 FROM study_spaces WHERE id = OLD.space_id "
            "AND user_id = OLD.user_id AND status = 'deleted') "
            if permanent
            else ""
        )
        op.execute(
            "CREATE TRIGGER learning_events_no_delete BEFORE DELETE ON learning_events "
            + condition
            + "BEGIN SELECT RAISE(ABORT, 'learning_events are append-only'); END"
        )
    else:
        exception = (
            "IF TG_OP = 'DELETE' AND EXISTS (SELECT 1 FROM study_spaces "
            "WHERE id = OLD.space_id AND user_id = OLD.user_id AND status = 'deleted') "
            "THEN RETURN OLD; END IF; "
            if permanent
            else ""
        )
        op.execute(
            "CREATE OR REPLACE FUNCTION reject_learning_event_mutation() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN "
            + exception
            + "RAISE EXCEPTION 'learning_events are append-only'; END; $$"
        )


def upgrade():
    with op.batch_alter_table("study_spaces") as batch:
        batch.alter_column("provider_id", existing_type=sa.String(36), nullable=True)
    set_event_guard(True)


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM study_spaces WHERE provider_id IS NULL LIMIT 1")).first():
        raise RuntimeError(
            "Cannot downgrade while permanent-deletion tombstones exist; preserve cleanup metadata"
        )
    # Remove the cross-table trigger before SQLite rebuilds its referenced table.
    set_event_guard(False)
    with op.batch_alter_table("study_spaces") as batch:
        batch.alter_column("provider_id", existing_type=sa.String(36), nullable=False)
