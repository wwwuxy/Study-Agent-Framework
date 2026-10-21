import pytest
from conftest import provider, register, space
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


def test_chat_limits_and_patch_whitelist():
    from app.schemas.chat import ChatSend, RequirementPatch

    assert ChatSend(content="每天15分钟", idempotency_key="one").retry is False
    for body in (
        {"content": "x" * 4001, "idempotency_key": "one"},
        {"content": " ", "idempotency_key": "one"},
    ):
        with pytest.raises(ValidationError):
            ChatSend(**body)
    assert "target_date" not in RequirementPatch().model_fields_set
    assert "target_date" in RequirementPatch(target_date=None).model_fields_set
    with pytest.raises(ValidationError):
        RequirementPatch(mastery=1)


def test_reply_cannot_smuggle_plan_changes():
    from app.schemas.chat import ChatDecision

    with pytest.raises(ValidationError):
        ChatDecision(kind="reply", reply="hello", patch={"daily_minutes": 15})
    with pytest.raises(ValidationError):
        ChatDecision(kind="update_plan", reply="done", patch={"daily_minutes": 15})


def test_chat_owner_and_active_turn_constraints(client):
    from app.db.models import ChatTurn, StudySpace

    register(client)
    sid = space(client, provider(client))
    with client.app.state.session_factory() as db:
        uid = db.get(StudySpace, sid).user_id
        db.add(
            ChatTurn(
                user_id=uid,
                space_id=sid,
                request_key="a",
                request_digest="a",
                content="a",
                active_space_id=sid,
            )
        )
        db.commit()
        db.add(
            ChatTurn(
                user_id=uid,
                space_id=sid,
                request_key="b",
                request_digest="b",
                content="b",
                active_space_id=sid,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert len(list(db.scalars(select(ChatTurn)))) == 1
