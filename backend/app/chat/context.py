import hashlib
import json

from sqlalchemy import select

from app.chat.contracts import ProviderSnapshot
from app.db.models import ChatTurn
from app.knowledge.materials import fingerprint
from app.planning.intent import read_intent


def concept_fingerprint(concepts):
    return hashlib.sha256(
        json.dumps(sorted(concepts, key=lambda c: c["key"]), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def snapshot_provider(config):
    return ProviderSnapshot(
        **{
            key: getattr(config, key) for key in ProviderSnapshot.__dataclass_fields__ if key != "fingerprint"
        },
        fingerprint=fingerprint(config),
    )


def build_context(db, space, message):
    from app.core.orchestrator import concept_data, next_action, profile
    from app.db.models import utcnow
    from app.reviews.sessions import list_reviews
    from app.teaching.lessons import unfinished_lesson

    rows = list(
        db.scalars(
            select(ChatTurn)
            .where(ChatTurn.space_id == space.id, ChatTurn.status == "completed")
            .order_by(ChatTurn.created_at.desc(), ChatTurn.id.desc())
            .limit(20)
        )
    )
    history = []
    length = 0
    for row in rows:
        size = len(row.content) + len(row.reply or "")
        if length + size > 24000:
            break
        history.append({"user": row.content, "assistant": row.reply})
        length += size
    lesson = unfinished_lesson(db, space)
    return {
        "task": "理解需求，必要时生成允许字段的计划修改和阶段路线；不要直接改写能力或记忆。",
        "message": message,
        "history": list(reversed(history)),
        "intent": read_intent(db, space),
        "concepts": concept_data(db, space.id),
        "learner_profile": profile(db, space),
        "next_action": next_action(db, space),
        "reviews": list_reviews(db, space, utcnow()),
        "current_lesson": {"id": lesson.id, "concept_ids": lesson.action["concept_ids"]} if lesson else None,
    }
