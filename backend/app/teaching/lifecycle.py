from sqlalchemy import select

from app.db.models import Lesson, ReviewSession
from app.providers.base import ProviderError
from app.teaching.lessons import unfinished_lesson
from app.teaching.presentation import public_lesson


def pause_current_lesson(db, space, *, reason, turn_id):
    lesson = unfinished_lesson(db, space)
    if not lesson:
        return None
    lesson.status = "paused"
    review = db.scalar(select(ReviewSession).where(ReviewSession.lesson_id == lesson.id))
    if review and review.status != "completed":
        review.status, review.active_concept = "paused", None
    db.flush()
    return lesson.id


def list_paused_lessons(db, space):
    return [
        public_lesson(db, row)
        for row in db.scalars(
            select(Lesson)
            .where(Lesson.space_id == space.id, Lesson.status == "paused")
            .order_by(Lesson.created_at.desc())
        )
    ]


def resume_lesson(db, space, lesson_id, request_key):
    lesson = db.scalar(select(Lesson).where(Lesson.space_id == space.id, Lesson.id == lesson_id))
    if not lesson:
        raise ProviderError("not_found", "课堂不存在", 404)
    active = unfinished_lesson(db, space)
    if active and active.id != lesson.id:
        raise ProviderError("active_lesson", "请先完成或暂存当前课堂", 409)
    if lesson.status == "active":
        return public_lesson(db, lesson)
    review = db.scalar(select(ReviewSession).where(ReviewSession.lesson_id == lesson.id))
    if review and review.status == "paused":
        other = db.scalar(
            select(ReviewSession).where(
                ReviewSession.space_id == space.id, ReviewSession.active_concept == review.concept_id
            )
        )
        if other:
            raise ProviderError("active_review", "该知识点已有活动复习", 409)
        review.status, review.active_concept = "active", review.concept_id
    lesson.status = "active"
    db.flush()
    return public_lesson(db, lesson)
