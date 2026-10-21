"""Each public function owns its transaction and Session in the calling DB thread."""

import base64
import json
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select

from app.api.deps import own_provider, own_space, session_user
from app.chat.context import build_context, concept_fingerprint, snapshot_provider
from app.chat.contracts import PreparedTurn, TurnResult
from app.db.models import (
    AgentRun,
    ChatTurn,
    PlanRevision,
    ProviderConfig,
    StudySpace,
    User,
    as_utc,
    new_id,
    utcnow,
)
from app.planning.intent import read_intent
from app.providers.base import ProviderError
from app.schemas.chat import ChatTurnPage, ChatTurnResponse, PlanRevisionPage


def public_turn(row):
    retry = row.status in {"failed", "conflict"} or (
        row.status == "processing" and row.lease_until and as_utc(row.lease_until) <= utcnow()
    )
    return ChatTurnResponse(
        id=row.id,
        study_space_id=row.space_id,
        content=row.content,
        idempotency_key=row.request_key,
        reply=row.reply,
        status=row.status,
        retry_allowed=bool(retry),
        created_at=as_utc(row.created_at).isoformat(),
        **row.result,
    )


def access(db, session_hash, space_id):
    user = session_user(db, session_hash, lock=True, lock_session=True)
    space = db.scalar(
        select(StudySpace).where(StudySpace.id == space_id, StudySpace.user_id == user.id).with_for_update()
    )
    if not space or space.status in {"deleted", "archived"}:
        raise ProviderError("not_found", "学习空间不存在", 404)
    return user, space


def prepare_turn(sessions, session_hash, space_id, body):
    from app.core.orchestrator import concept_data, digest

    with sessions.begin() as db:
        user, space = access(db, session_hash, space_id)
        hashed = digest({"space_id": space_id, "content": body.content})
        active = db.scalar(select(ChatTurn).where(ChatTurn.active_space_id == space_id))
        if active and (not active.lease_until or as_utc(active.lease_until) <= utcnow()):
            active.status = "failed"
            active.active_space_id = None
            active.lease_token = None
            active.result = {
                "outcome": "failed",
                "error_code": "chat_interrupted",
                "error_message": "上次处理已中断，可重试同一消息",
            }
            db.flush()
        row = db.scalar(
            select(ChatTurn).where(
                ChatTurn.space_id == space_id, ChatTurn.request_key == body.idempotency_key
            )
        )
        if row:
            if row.request_digest != hashed:
                raise ProviderError("idempotency_conflict", "同一请求标识不能发送不同消息", 409)
            if row.status == "completed" or not body.retry:
                return TurnResult(202 if row.status == "processing" else 200, public_turn(row))
            if row.status == "processing":
                return TurnResult(202, public_turn(row))
            if row.status not in {"failed", "conflict"}:
                return TurnResult(200, public_turn(row))
        if db.scalar(select(ChatTurn.id).where(ChatTurn.active_space_id == space_id)):
            raise ProviderError("chat_busy", "该空间正在处理一条消息，请等待结果", 409)
        config = own_provider(db, user.id, space.provider_id, require_tested=True)
        if row is None:
            row = ChatTurn(
                id=new_id(),
                user_id=user.id,
                space_id=space_id,
                request_key=body.idempotency_key,
                request_digest=hashed,
                content=body.content,
            )
            db.add(row)
        row.status = "processing"
        row.active_space_id = space_id
        row.reply = None
        row.result = {}
        row.provider_id = config.id
        row.lease_token = new_id()
        row.lease_until = utcnow() + timedelta(seconds=180)
        db.flush()
        snapshot = snapshot_provider(config)
        version = read_intent(db, space)["version"]
        graph = concept_fingerprint(concept_data(db, space_id))
        row.baseline = {
            "intent_version": version,
            "concept_fingerprint": graph,
            "provider_fingerprint": snapshot.fingerprint,
        }
        task = build_context(db, space, body.content)
        return PreparedTurn(
            row.id, space_id, user.id, session_hash, row.lease_token, version, graph, snapshot, task
        )


def audit(db, prepared, call):
    config = db.get(ProviderConfig, prepared.provider_snapshot.id)
    if not config or config.user_id != prepared.user_id:
        return None
    record = AgentRun(
        id=new_id(),
        user_id=prepared.user_id,
        space_id=prepared.space_id,
        provider_id=config.id,
        model=prepared.provider_snapshot.chat_model,
        step="planning_chat",
        elapsed_ms=call.elapsed_ms,
        usage=call.usage,
        error_code=call.error.code if call.error else None,
    )
    db.add(record)
    db.flush()
    return record.id


def publish_turn(sessions, prepared, call):
    from app.chat.application import apply_decision
    from app.core.orchestrator import concept_data
    from app.knowledge.materials import fingerprint

    with sessions.begin() as db:
        _, space = access(db, prepared.session_hash, prepared.space_id)
        row = db.scalar(
            select(ChatTurn)
            .where(ChatTurn.id == prepared.turn_id, ChatTurn.space_id == space.id)
            .with_for_update()
        )
        if row is None:
            raise ProviderError("not_found", "聊天记录不存在", 404)
        if row.status != "processing" or row.lease_token != prepared.lease_token:
            return TurnResult(202 if row.status == "processing" else 200, public_turn(row))
        if as_utc(row.lease_until) <= utcnow():
            raise ProviderError("chat_interrupted", "处理租约已过期，请重试", 409)
        config = db.get(ProviderConfig, space.provider_id)
        stale = (
            read_intent(db, space)["version"] != prepared.intent_version
            or concept_fingerprint(concept_data(db, space.id)) != prepared.concept_fingerprint
            or not config
            or config.id != prepared.provider_snapshot.id
            or fingerprint(config) != prepared.provider_snapshot.fingerprint
        )
        row.agent_run_id = audit(db, prepared, call)
        if stale:
            row.status = "conflict"
            row.reply = None
            row.result = {
                "outcome": "conflict",
                "error_code": "chat_context_changed",
                "error_message": "处理期间需求、教材或模型发生变化，本次未应用；请重试",
            }
        elif call.error:
            row.status = "failed"
            row.reply = None
            row.result = {
                "outcome": "failed",
                "error_code": call.error.code,
                "error_message": call.error.message,
            }
        else:
            result = apply_decision(db, space, row, call.validated)
            row.status = "completed"
            row.reply = call.validated.reply
            row.result = {
                "outcome": result.outcome,
                "changes": result.changes,
                "revision_id": result.revision_id,
                "plan": result.plan,
            }
        row.active_space_id = None
        row.lease_token = None
        db.flush()
        return TurnResult(201, public_turn(row))


def fail_turn(sessions, prepared, error, call=None):
    with sessions.begin() as db:
        db.scalar(select(User).where(User.id == prepared.user_id).with_for_update())
        space = db.scalar(select(StudySpace).where(StudySpace.id == prepared.space_id).with_for_update())
        if not space or space.status == "deleted":
            raise ProviderError("not_found", "学习空间不存在", 404)
        row = db.scalar(
            select(ChatTurn)
            .where(ChatTurn.id == prepared.turn_id, ChatTurn.user_id == prepared.user_id)
            .with_for_update()
        )
        if row is None:
            raise ProviderError("not_found", "聊天记录不存在", 404)
        if row.status == "processing" and row.lease_token == prepared.lease_token:
            if call is not None and error.code not in {"unauthenticated", "not_found"}:
                from app.chat.contracts import ModelCallResult

                row.agent_run_id = audit(
                    db, prepared, ModelCallResult(None, call.elapsed_ms, call.usage, error)
                )
            row.status = "cancelled" if error.code in {"unauthenticated", "not_found"} else "failed"
            row.reply = None
            row.result = {"outcome": row.status, "error_code": error.code, "error_message": error.message}
            row.active_space_id = None
            row.lease_token = None
            db.flush()
        return TurnResult(200, public_turn(row))


def cursor_for(row):
    return (
        base64.urlsafe_b64encode(json.dumps([as_utc(row.created_at).isoformat(), row.id]).encode())
        .decode()
        .rstrip("=")
    )


def parse_cursor(before):
    try:
        if len(before) > 512:
            raise ValueError()
        at, key = json.loads(
            base64.b64decode(before + "=" * (-len(before) % 4), altchars=b"-_", validate=True)
        )
        stamp = datetime.fromisoformat(at)
        if stamp.tzinfo is None or not isinstance(key, str) or len(key) > 36:
            raise ValueError()
        return stamp, key
    except (ValueError, TypeError, UnicodeError):
        raise ProviderError("invalid_cursor", "历史分页标识无效", 422) from None


def read_history(sessions, session_hash, space_id, *, before=None, limit=30, revisions=False, turn_id=None):
    with sessions() as db:
        user = session_user(db, session_hash)
        own_space(db, user.id, space_id)
        if turn_id:
            row = db.scalar(select(ChatTurn).where(ChatTurn.space_id == space_id, ChatTurn.id == turn_id))
            if not row:
                raise ProviderError("not_found", "聊天记录不存在", 404)
            return public_turn(row)
        model = PlanRevision if revisions else ChatTurn
        query = select(model).where(model.space_id == space_id)
        if before:
            at, key = parse_cursor(before)
            query = query.where(or_(model.created_at < at, and_(model.created_at == at, model.id < key)))
        rows = list(db.scalars(query.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)))
        next_cursor = cursor_for(rows[limit - 1]) if len(rows) > limit else None
        rows = rows[:limit]
        if revisions:
            return PlanRevisionPage(
                items=[
                    {
                        "id": r.id,
                        "version": r.version,
                        "turn_id": r.turn_id,
                        **r.data,
                        "created_at": as_utc(r.created_at).isoformat(),
                    }
                    for r in rows
                ],
                next_cursor=next_cursor,
            )
        return ChatTurnPage(items=[public_turn(r) for r in reversed(rows)], next_cursor=next_cursor)
