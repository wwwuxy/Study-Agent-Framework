from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.activity.calendar import local_day
from app.activity.presentation import task_view
from app.activity.snapshot import read_snapshot
from app.db.models import AssessmentAttempt, DailyTask, LearningEvent, Lesson, User, as_utc
from app.planning.intent import effective_scope
from app.providers.base import ProviderError
from app.schemas.activity import TaskStartResponse


def own_task(db, space, task_id):
    task = db.scalar(
        select(DailyTask)
        .where(DailyTask.id == task_id, DailyTask.space_id == space.id, DailyTask.user_id == space.user_id)
        .with_for_update()
    )
    if not task:
        raise ProviderError("not_found", "学习任务不存在", 404)
    return task


def refresh_completion(db, space, now):
    attempted = set(
        db.scalars(select(AssessmentAttempt.item_id).where(AssessmentAttempt.space_id == space.id))
    )
    changed = 0
    for task in db.scalars(
        select(DailyTask).where(DailyTask.space_id == space.id, DailyTask.status == "in_progress")
    ):
        ids = task.data.get("item_ids", [])
        lesson = db.get(Lesson, task.lesson_id) if task.lesson_id else None
        if ids and set(ids) <= attempted and (not lesson or lesson.completed):
            events = db.scalars(select(LearningEvent).where(LearningEvent.space_id == space.id)).all()
            dates = [
                as_utc(e.occurred_at)
                for e in events
                if e.data.get("assessment_item_id") in ids
                or (
                    task.lesson_id
                    and e.type == "learning_task_completed"
                    and e.data.get("lesson_id") == task.lesson_id
                )
            ]
            task.status, task.active_cycle_key = "completed", None
            task.data = {**task.data, "completed_at": max(dates, default=now).isoformat()}
            changed += 1
    db.flush()
    return changed


async def start_daily_task(request, db, space, task_id):
    from app.db.models import utcnow
    from app.reviews.sessions import start_review
    from app.schemas.adaptive import ReviewStart
    from app.teaching.diagnostics import ensure_diagnostics
    from app.teaching.lessons import create_lesson, unfinished_lesson
    from app.teaching.presentation import public_lesson

    task = own_task(db, space, task_id)
    if task.status in {"postponed", "skipped", "superseded"}:
        raise ProviderError("task_closed", "该安排已结束，请刷新今日任务", 409)
    if task.data.get("start_receipt"):
        return TaskStartResponse.model_validate(task.data["start_receipt"])
    if task.status != "pending" or task.data.get("blocking_reason"):
        raise ProviderError("task_not_ready", "该任务暂不可执行，请刷新今日安排", 409)
    now = utcnow()
    snapshot = read_snapshot(db, space, now)
    scope = effective_scope(snapshot.concepts, snapshot.intent)["included_ids"]
    if task.concept_id not in scope or task.data.get("fingerprint") != snapshot.fingerprint:
        raise ProviderError("plan_changed", "学习状态或需求已变化，请刷新今日安排", 409)
    existing = unfinished_lesson(db, space)
    kind = "lesson"
    if existing:
        if existing.action["concept_ids"][0] != task.concept_id:
            raise ProviderError("unfinished_lesson", "请先继续当前课堂", 409)
        result = public_lesson(db, existing)
    elif task.action == "DIAGNOSE":
        kind = "diagnostic"
        result = await ensure_diagnostics(request, db, space)
    elif task.action == "REVIEW":
        result = (
            await start_review(
                request,
                db,
                space,
                ReviewStart(concept_id=task.concept_id, idempotency_key="m4_task_" + task.id),
            )
        )["lesson"]
    else:
        action = task.data["action"]
        concept = next(c for c in snapshot.concepts if c["key"] == task.concept_id)
        if not all(snapshot.states.get(p, {}).get("status") == "mastered" for p in concept["prerequisites"]):
            raise ProviderError("prerequisites_unmet", "前置知识证据不足", 409)
        result = await create_lesson(request, db, space, action, "m4_task_" + task.id)
    ids = [q["id"] for q in result["items" if kind == "diagnostic" else "exercises"]]
    task.status = "in_progress"
    task.lesson_id = result["id"] if kind == "lesson" else None
    task.data = {**task.data, "item_ids": ids, "started_at": now.isoformat()}
    receipt = TaskStartResponse(
        task=task_view(task), execution_kind=kind, lesson_id=task.lesson_id, item_ids=ids
    )
    task.data = {**task.data, "start_receipt": receipt.model_dump()}
    return receipt


def complete_task(db, space, task_id, now):
    task = own_task(db, space, task_id)
    refresh_completion(db, space, now)
    if task.status != "completed":
        raise ProviderError("task_not_complete", "完成课堂阅读并提交所有关联题目后，才能确认完成", 409)
    return task_view(task)


def set_task_disposition(db, space, task_id, status, now):
    task = own_task(db, space, task_id)
    if task.status in {"completed", "superseded"}:
        raise ProviderError("task_closed", "该任务已结束", 409)
    if task.status == status:
        return task_view(task)
    task.status, task.active_cycle_key = status, None
    task.data = {**task.data, "disposed_at": now.isoformat()}
    if status == "postponed":
        day = local_day(now, db.get(User, space.user_id).timezone)
        task.data = {
            **task.data,
            "postponed_until": (
                day.start.astimezone(ZoneInfo(day.timezone)).date() + timedelta(days=1)
            ).isoformat(),
        }
    return task_view(task)


def cancel_space_activity(db, space, now):
    from app.db.models import AnalysisRun, PeriodicJob

    for model in (PeriodicJob, AnalysisRun):
        for row in db.scalars(select(model).where(model.space_id == space.id).with_for_update()):
            row.status, row.lease_token, row.lease_until = "cancelled", None, now
    db.flush()
