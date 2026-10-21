from sqlalchemy import select

from app.core.orchestrator import public_item
from app.db.models import AssessmentAttempt, AssessmentItem, ReviewSession
from app.knowledge.materials import resolve_sources


def attempts_map(db, space_id):
    return {
        a.item_id: a.result
        for a in db.scalars(select(AssessmentAttempt).where(AssessmentAttempt.space_id == space_id)).all()
    }


def public_question(db, item, attempted):
    citations = resolve_sources(db, item.space_id, item.data.get("source_ids", []))
    return {
        **public_item(item, attempted),
        "source_ids": [s["source_id"] for s in citations],
        "citations": citations,
        "grounding": "user_material" if citations else "model_generated_unverified",
    }


def public_lesson(db, lesson):
    items = db.scalars(
        select(AssessmentItem).where(AssessmentItem.lesson_id == lesson.id).order_by(AssessmentItem.id)
    ).all()
    attempted = attempts_map(db, lesson.space_id)
    return {
        "id": lesson.id,
        "review_id": db.scalar(select(ReviewSession.id).where(ReviewSession.lesson_id == lesson.id)),
        "action": lesson.action,
        **lesson.content,
        "completed": lesson.completed,
        "status": lesson.status,
        "grounding": "user_material" if lesson.content.get("source_ids") else "model_generated_unverified",
        "citations": resolve_sources(db, lesson.space_id, lesson.content.get("source_ids", [])),
        "exercises": [public_question(db, i, attempted) for i in items],
        "attempts": attempted,
    }
