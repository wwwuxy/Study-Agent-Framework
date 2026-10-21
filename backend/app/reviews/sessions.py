from sqlalchemy import select

from app.core.orchestrator import concept_data, profile
from app.db.models import Lesson, ReviewSession, ReviewState, as_utc, new_id, utcnow
from app.providers.base import ProviderError
from app.reviews.state import memory_states
from app.teaching.lessons import create_lesson, unfinished_lesson
from app.teaching.presentation import public_lesson


def list_reviews(db, space, now):
    groups = {"due": [], "upcoming": [], "unassessed": [], "as_of": now.isoformat()}
    from app.planning.intent import effective_scope, read_intent

    included = effective_scope(concept_data(db, space.id), read_intent(db, space))["included_ids"]
    names = {c["key"]: c["name"] for c in concept_data(db, space.id)}
    for key, row in sorted(memory_states(db, space, now).items(), key=lambda pair: (pair[1]["due"], pair[0])):
        groups[row["status"]].append(
            {**row, "name": names.get(key, key), "in_current_scope": key in included}
        )
    return groups


def get_review(db, space, review_id):
    row = db.scalar(
        select(ReviewSession).where(
            ReviewSession.id == review_id,
            ReviewSession.space_id == space.id,
            ReviewSession.user_id == space.user_id,
        )
    )
    if not row:
        raise ProviderError("not_found", "复习会话不存在", 404)
    return {
        "id": row.id,
        "concept_id": row.concept_id,
        "status": row.status,
        "scheduled_for": as_utc(row.scheduled_for).isoformat(),
        "lesson": public_lesson(db, db.get(Lesson, row.lesson_id)),
    }


async def start_review(request, db, space, body):
    existing = db.scalar(
        select(ReviewSession).where(
            ReviewSession.space_id == space.id, ReviewSession.request_key == body.idempotency_key
        )
    )
    if existing:
        if existing.concept_id != body.concept_id:
            raise ProviderError("idempotency_conflict", "同一复习请求键不能用于不同知识点", 409)
        return get_review(db, space, existing.id)
    active = db.scalar(
        select(ReviewSession).where(
            ReviewSession.space_id == space.id, ReviewSession.active_concept == body.concept_id
        )
    )
    if active:
        return get_review(db, space, active.id)
    card = db.scalar(
        select(ReviewState)
        .where(
            ReviewState.space_id == space.id,
            ReviewState.user_id == space.user_id,
            ReviewState.concept_id == body.concept_id,
        )
        .with_for_update()
    )
    if not card:
        raise ProviderError("not_found", "知识点不存在", 404)
    now = utcnow()
    if card.card.get("last_review") is None or as_utc(card.due) > now:
        raise ProviderError("review_not_due", "该知识点尚未形成复习证据或尚未到期", 422)
    concepts = {c["key"]: c for c in concept_data(db, space.id)}
    states = {s["concept_id"]: s for s in profile(db, space)["states"]}
    if not all(
        states.get(key, {}).get("status") == "mastered" for key in concepts[body.concept_id]["prerequisites"]
    ):
        raise ProviderError("prerequisites_unmet", "前置知识证据不足，请先补齐基础", 422)
    if unfinished_lesson(db, space):
        raise ProviderError("unfinished_lesson", "请先完成当前课堂及练习，再开始复习", 409)
    rid = new_id()
    action = {
        "action": "REVIEW",
        "teaching_mode": "spaced_review",
        "concept_ids": [body.concept_id],
        "reason": "FSRS 复习已到期，使用新的单知识点题目验证独立回忆",
        "estimated_minutes": min(10, space.daily_minutes),
        "evidence_event_ids": [],
        "policy_version": "policy_v2",
        "requires_followup_assessment": True,
    }
    lesson = await create_lesson(request, db, space, action, "review_" + rid, review_id=rid)
    db.add(
        ReviewSession(
            id=rid,
            user_id=space.user_id,
            space_id=space.id,
            concept_id=body.concept_id,
            active_concept=body.concept_id,
            lesson_id=lesson["id"],
            item_id=lesson["exercises"][0]["id"],
            request_key=body.idempotency_key,
            scheduled_for=card.due,
        )
    )
    db.flush()
    return get_review(db, space, rid)
