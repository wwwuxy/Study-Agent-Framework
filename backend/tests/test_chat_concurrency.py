import asyncio
import os
import threading

import httpx
import pytest
from conftest import provider, register, space
from sqlalchemy import select


def test_answer_during_chat_and_deleted_space_do_not_resurrect(client):
    from app.db.models import AgentRun, ChatTurn, LearningEvent, PlanRevision
    from app.providers.fake import FakeAdapter

    register(client)
    sid = space(client, provider(client))
    root = f"/api/v1/study-spaces/{sid}"
    q = client.post(root + "/diagnostics").json()["items"][0]
    started, release = threading.Event(), threading.Event()

    class Controlled(FakeAdapter):
        async def generate_structured(self, messages, schema):
            if schema.get("title") == "ChatDecision":
                started.set()
                assert await asyncio.to_thread(release.wait, 5)
            return await super().generate_structured(messages, schema)

    client.app.state.adapter_factory = lambda _: Controlled()

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app),
            base_url="http://testserver",
            cookies=dict(client.cookies),
            timeout=5,
        ) as http:
            request = asyncio.create_task(
                http.post(root + "/chat/turns", json={"content": "每天15分钟", "idempotency_key": "chat"})
            )
            assert await asyncio.to_thread(started.wait, 3)
            try:
                assert (await asyncio.wait_for(http.get("/health"), 1)).status_code == 200
                a = await asyncio.wait_for(
                    http.post(
                        root + "/attempts",
                        json={"item_id": q["id"], "answer": "A", "idempotency_key": "answer"},
                    ),
                    1,
                )
                assert a.status_code == 201, a.text
                assert (
                    await http.post(
                        root + "/chat/turns", json={"content": "another", "idempotency_key": "other"}
                    )
                ).status_code == 409
                assert (await http.delete(root)).status_code == 200
            finally:
                release.set()
            response = await request
            assert response.status_code == 404, response.text

    asyncio.run(scenario())
    with client.app.state.session_factory() as db:
        assert not list(db.scalars(select(ChatTurn)))
        assert not list(db.scalars(select(PlanRevision)))
        assert not list(db.scalars(select(LearningEvent)))
        assert not list(db.scalars(select(AgentRun).where(AgentRun.space_id == sid)))


def test_context_change_and_lease_loser_cannot_apply(client):
    from app.chat.contracts import ModelCallResult
    from app.chat.turns import prepare_turn, publish_turn
    from app.core.security import token_hash
    from app.db.models import ChatTurn, StudySpace
    from app.schemas.chat import ChatDecision, ChatSend

    register(client)
    sid = space(client, provider(client))
    sessions = client.app.state.session_factory
    hashed = token_hash(client.cookies.get("study_session"))
    prepared = prepare_turn(sessions, hashed, sid, ChatSend(content="15分钟", idempotency_key="one"))
    with sessions() as db:
        t = db.get(ChatTurn, prepared.turn_id)
        t.lease_token = "new-owner"
        db.commit()
    call = ModelCallResult(
        ChatDecision(kind="update_plan", reply="建议", patch={"daily_minutes": 15}, reason="用户要求"), 1, {}
    )
    assert publish_turn(sessions, prepared, call).http_status == 202
    with sessions() as db:
        assert db.get(StudySpace, sid).daily_minutes == 30
        t = db.get(ChatTurn, prepared.turn_id)
        t.lease_token = prepared.lease_token
        s = db.get(StudySpace, sid)
        s.expected_level = "changed outside chat"
        db.commit()
    # Provider changes invalidate the snapshot; unrelated answers do not.
    from app.db.models import ProviderConfig

    with sessions() as db:
        s = db.get(StudySpace, sid)
        config = db.get(ProviderConfig, s.provider_id)
        config.chat_model = "changed"
        db.commit()
    assert publish_turn(sessions, prepared, call).response.outcome == "conflict"


def test_session_is_rechecked_after_user_lock_wait(client, monkeypatch):
    import pytest
    from sqlalchemy import delete

    from app.api.deps import session_user
    from app.core.security import token_hash
    from app.db.models import AuthSession, User
    from app.providers.base import ProviderError

    register(client)
    hashed = token_hash(client.cookies.get("study_session"))
    sessions = client.app.state.session_factory
    with sessions() as db:
        scalar = db.scalar
        revoked = False

        def revoke_before_user_lock(statement, *args, **kwargs):
            nonlocal revoked
            if not revoked and any(d.get("entity") is User for d in statement.column_descriptions):
                revoked = True
                with sessions.begin() as other:
                    other.execute(delete(AuthSession).where(AuthSession.token_hash == hashed))
            return scalar(statement, *args, **kwargs)

        monkeypatch.setattr(db, "scalar", revoke_before_user_lock)
        with pytest.raises(ProviderError) as error:
            session_user(db, hashed, lock=True)
        assert error.value.code == "unauthenticated"


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="requires PostgreSQL row locks")
def test_logout_wait_does_not_block_health(client):
    from sqlalchemy import event

    from app.core.security import token_hash
    from app.db.models import AuthSession

    register(client)
    hashed = token_hash(client.cookies.get("study_session"))
    waiting = threading.Event()
    engine = client.app.state.engine

    @event.listens_for(engine, "before_cursor_execute")
    def observe_delete(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("DELETE FROM auth_sessions"):
            waiting.set()

    with client.app.state.session_factory() as holder:
        holder.scalar(select(AuthSession).where(AuthSession.token_hash == hashed).with_for_update())

        async def scenario():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=client.app),
                base_url="http://testserver",
                cookies=dict(client.cookies),
            ) as http:
                logout = asyncio.create_task(http.post("/api/v1/auth/logout"))
                try:
                    assert await asyncio.to_thread(waiting.wait, 3)
                    assert (await asyncio.wait_for(http.get("/health"), 1)).status_code == 200
                finally:
                    holder.rollback()
                assert (await logout).status_code == 204

        asyncio.run(scenario())
    event.remove(engine, "before_cursor_execute", observe_delete)
