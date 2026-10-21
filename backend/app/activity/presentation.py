import base64
import json

from sqlalchemy import and_, or_, select

from app.db.models import as_utc
from app.providers.base import ProviderError
from app.schemas.activity import DailyTaskResponse, Page


def task_view(row):
    return DailyTaskResponse(
        id=row.id,
        study_space_id=row.space_id,
        plan_id=row.plan_id,
        concept_id=row.concept_id,
        name=row.data.get("name", row.concept_id),
        action=row.action,
        estimated_minutes=row.estimated_minutes,
        status=row.status,
        reason=row.data.get("reason", ""),
        blocking_reason=row.data.get("blocking_reason"),
        lesson_id=row.lesson_id,
        item_ids=row.data.get("item_ids", []),
        created_at=as_utc(row.created_at).isoformat(),
    )


def owned_page(db, model, user_id, projection, cursor=None, limit=30, *, space_id=None):
    scope = f"{model.__tablename__}:{user_id}:{space_id or ''}"
    query = select(model).where(model.user_id == user_id)
    if space_id:
        query = query.where(model.space_id == space_id)
    if cursor:
        try:
            value = json.loads(base64.urlsafe_b64decode(cursor).decode())
            if value["scope"] != scope:
                raise ValueError()
            from datetime import datetime

            at = datetime.fromisoformat(value["at"])
            query = query.where(
                or_(model.created_at < at, and_(model.created_at == at, model.id < value["id"]))
            )
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise ProviderError("invalid_cursor", "分页位置无效", 422) from None
    rows = db.scalars(query.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)).all()
    token = None
    if len(rows) > limit:
        row = rows[limit - 1]
        token = base64.urlsafe_b64encode(
            json.dumps({"scope": scope, "at": as_utc(row.created_at).isoformat(), "id": row.id}).encode()
        ).decode()
    return Page(items=[projection(row) for row in rows[:limit]], next_cursor=token)
