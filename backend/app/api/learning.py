from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.api.deps import current_user, get_db, own_provider, own_space
from app.core.orchestrator import (
    append_event,
    call_model,
    next_action,
)
from app.db.models import AssessmentItem, LearningEvent, Lesson
from app.knowledge.materials import resolve_sources
from app.providers.base import ProviderError
from app.schemas.api import AttemptSubmit, IdempotentRequest
from app.schemas.domain import Hint
from app.teaching.presentation import attempts_map, public_lesson

router = APIRouter(prefix="/study-spaces/{space_id}", tags=["learning"])


def item_in_space(db, space, item_id):
    item = db.scalar(
        select(AssessmentItem).where(AssessmentItem.id == item_id, AssessmentItem.space_id == space.id)
    )
    if not item:
        raise ProviderError("not_found", "题目不存在", 404)
    return item


@router.get("/lessons/paused")
async def paused_lessons(space_id: str, db=Depends(get_db), user=Depends(current_user)):
    from app.teaching.lifecycle import list_paused_lessons

    return list_paused_lessons(db, own_space(db, user.id, space_id))


@router.post("/lessons/{lesson_id}/resume")
async def resume(
    space_id: str, lesson_id: str, body: IdempotentRequest, db=Depends(get_db), user=Depends(current_user)
):
    from app.teaching.lifecycle import resume_lesson

    return resume_lesson(db, own_space(db, user.id, space_id), lesson_id, body.idempotency_key)


@router.post("/diagnostics")
async def diagnostics(space_id: str, request: Request, db=Depends(get_db), user=Depends(current_user)):
    from app.teaching.diagnostics import ensure_diagnostics

    return await ensure_diagnostics(request, db, own_space(db, user.id, space_id))


@router.get("/next-action")
async def action(space_id: str, db=Depends(get_db), user=Depends(current_user)):
    return next_action(db, own_space(db, user.id, space_id))


@router.get("/lessons/current")
async def current_lesson(space_id: str, db=Depends(get_db), user=Depends(current_user)):
    space = own_space(db, user.id, space_id)
    from app.teaching.lessons import unfinished_lesson

    active = unfinished_lesson(db, space)
    if active:
        return public_lesson(db, active)
    lesson = db.scalar(
        select(Lesson)
        .where(Lesson.space_id == space.id, Lesson.status == "active")
        .order_by(Lesson.created_at.desc())
        .limit(1)
    )
    return public_lesson(db, lesson) if lesson else None


@router.post("/lessons")
async def generate_lesson(
    space_id: str, body: IdempotentRequest, request: Request, db=Depends(get_db), user=Depends(current_user)
):
    from app.teaching.lessons import create_lesson, unfinished_lesson

    space = own_space(db, user.id, space_id)
    existing = db.scalar(
        select(Lesson).where(Lesson.space_id == space.id, Lesson.init_key == body.idempotency_key)
    )
    if existing:
        return public_lesson(db, existing)
    active = unfinished_lesson(db, space)
    if active:
        return public_lesson(db, active)
    action = next_action(db, space)
    if action["action"] == "REVIEW":
        from app.reviews.sessions import start_review
        from app.schemas.adaptive import ReviewStart

        review = await start_review(
            request,
            db,
            space,
            ReviewStart(concept_id=action["concept_ids"][0], idempotency_key=body.idempotency_key),
        )
        return review["lesson"]
    return await create_lesson(request, db, space, action, body.idempotency_key)


@router.post("/lessons/{lesson_id}/complete")
async def complete(
    space_id: str, lesson_id: str, body: IdempotentRequest, db=Depends(get_db), user=Depends(current_user)
):
    space = own_space(db, user.id, space_id)
    lesson = db.scalar(select(Lesson).where(Lesson.space_id == space.id, Lesson.id == lesson_id))
    if not lesson:
        raise ProviderError("not_found", "课堂不存在", 404)
    if not lesson.completed:
        append_event(
            db,
            space,
            "lesson_viewed",
            body.idempotency_key,
            {"lesson_id": lesson.id, "concept_ids": lesson.action["concept_ids"]},
        )
        lesson.completed = True
    from app.teaching.attempts import maybe_complete_task

    maybe_complete_task(db, lesson)
    return {"completed": True, "notice": "已记录阅读经历；掌握状态需要作答证据。"}


@router.post("/items/{item_id}/hint")
async def hint(
    space_id: str,
    item_id: str,
    body: IdempotentRequest,
    request: Request,
    db=Depends(get_db),
    user=Depends(current_user),
):
    space = own_space(db, user.id, space_id)
    item = item_in_space(db, space, item_id)
    if item.id in attempts_map(db, space.id):
        raise ProviderError("already_answered", "该题已作答，请查看反馈", 409)
    previous = db.scalars(
        select(LearningEvent).where(
            LearningEvent.space_id == space.id, LearningEvent.type == "hint_requested"
        )
    ).all()
    for event in previous:
        if event.data["assessment_item_id"] == item.id:
            return {"hint": event.data["hint"], "event_id": event.id}
    config = own_provider(db, user.id, space.provider_id, require_tested=True)
    content, _ = await call_model(
        request,
        db,
        config,
        space.id,
        "hint",
        Hint,
        {
            "task": "给出引导性提示，不直接泄露答案",
            "question": item.data["prompt"],
            "options": item.data["options"],
            "sources": resolve_sources(db, space.id, item.data.get("source_ids", [])),
        },
    )
    event = append_event(
        db,
        space,
        "hint_requested",
        body.idempotency_key,
        {"assessment_item_id": item.id, "concept_ids": item.data["concept_keys"], "hint": content.hint},
    )
    return {"hint": content.hint, "event_id": event.id}


@router.post("/attempts", status_code=201)
async def submit(
    space_id: str, body: AttemptSubmit, request: Request, db=Depends(get_db), user=Depends(current_user)
):
    from app.teaching.attempts import submit_attempt

    return await submit_attempt(request, db, own_space(db, user.id, space_id), body)
