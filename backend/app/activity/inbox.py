from sqlalchemy import select

from app.activity.presentation import owned_page
from app.db.models import InboxMessage, as_utc
from app.providers.base import ProviderError
from app.schemas.activity import InboxResponse


def message_view(row):
    return InboxResponse(
        id=row.id,
        study_space_id=row.space_id,
        kind=row.kind,
        title=row.data["title"],
        summary=row.data["summary"],
        source_kind=row.data["source_kind"],
        source_id=row.data["source_id"],
        read_at=as_utc(row.read_at).isoformat() if row.read_at else None,
        created_at=as_utc(row.created_at).isoformat(),
    )


def put_message(db, space, event_key, kind, source_id, summary, now):
    row = db.scalar(
        select(InboxMessage).where(InboxMessage.space_id == space.id, InboxMessage.event_key == event_key)
    )
    if not row:
        row = InboxMessage(
            user_id=space.user_id, space_id=space.id, event_key=event_key, kind=kind, created_at=now
        )
        db.add(row)
    titles = {"due": "复习已到期", "deviation": "学习安排建议", "weekly": "学习周报已生成"}
    row.data = {
        "title": titles[kind],
        "summary": summary,
        "source_id": source_id,
        "source_kind": {"due": "daily_plan", "deviation": "suggestion", "weekly": "weekly_summary"}[kind],
    }
    db.flush()
    return message_view(row)


def list_inbox(db, user_id, cursor=None, limit=30):
    return owned_page(db, InboxMessage, user_id, message_view, cursor, limit)


def read_message(db, user_id, message_id, now):
    row = db.scalar(
        select(InboxMessage).where(InboxMessage.user_id == user_id, InboxMessage.id == message_id)
    )
    if not row:
        raise ProviderError("not_found", "消息不存在", 404)
    if not row.read_at:
        row.read_at = now
    return message_view(row)
