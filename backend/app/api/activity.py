from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from app.activity.daily import coordinate_day, today_plan
from app.activity.db_phase import activity_db
from app.activity.inbox import list_inbox, read_message
from app.activity.presentation import owned_page, task_view
from app.activity.queue import job_view, retry_activity_job
from app.activity.suggestions import apply_suggestion, suggestion_view
from app.activity.tasks import complete_task, set_task_disposition, start_daily_task
from app.api.deps import current_user, get_db, own_space
from app.core.security import token_hash
from app.db.models import DailyTask, InboxMessage, LearningSuggestion, PeriodicJob, utcnow
from app.schemas.activity import (
    ActivityJobResponse,
    DailyPlanResponse,
    DailyTaskResponse,
    InboxResponse,
    Page,
    SuggestionResponse,
    TaskStartResponse,
    TodayResponse,
    UnreadCountResponse,
    WeeklySummaryResponse,
)
from app.schemas.api import IdempotentRequest

router = APIRouter(tags=["active-learning"])
SPACE = "/study-spaces/{space_id}"


@router.get(SPACE + "/daily-plans/today", response_model=TodayResponse)
async def today(space_id: str, db=Depends(get_db), user=Depends(current_user)):
    return today_plan(db, user.id, space_id, utcnow())


@router.post(SPACE + "/daily-plans/refresh", response_model=DailyPlanResponse)
async def refresh(space_id: str, request: Request, body: IdempotentRequest):
    # A short own-session transaction avoids holding get_db's SQLite lock twice.
    from app.api.deps import session_user

    def run(factory):
        with factory() as db:
            user = session_user(db, token_hash(request.cookies.get("study_session", "")))
            own_space(db, user.id, space_id)
            uid = user.id
        return coordinate_day(factory, uid, space_id, utcnow())

    return await activity_db(request.app, run)


@router.get(SPACE + "/tasks", response_model=list[DailyTaskResponse])
async def tasks(
    space_id: str,
    status: str | None = Query(None, max_length=20),
    db=Depends(get_db),
    user=Depends(current_user),
):
    space = own_space(db, user.id, space_id)
    query = select(DailyTask).where(DailyTask.space_id == space.id)
    if status:
        query = query.where(DailyTask.status == status)
    return [task_view(t) for t in db.scalars(query.order_by(DailyTask.created_at.desc()).limit(100))]


@router.post(SPACE + "/tasks/{task_id}/start", response_model=TaskStartResponse)
async def start(
    space_id: str,
    task_id: str,
    request: Request,
    body: IdempotentRequest,
    db=Depends(get_db),
    user=Depends(current_user),
):
    return await start_daily_task(request, db, own_space(db, user.id, space_id), task_id)


@router.post(SPACE + "/tasks/{task_id}/complete", response_model=DailyTaskResponse)
async def complete(
    space_id: str, task_id: str, body: IdempotentRequest, db=Depends(get_db), user=Depends(current_user)
):
    return complete_task(db, own_space(db, user.id, space_id), task_id, utcnow())


@router.post(SPACE + "/tasks/{task_id}/skip", response_model=DailyTaskResponse)
async def skip(
    space_id: str, task_id: str, body: IdempotentRequest, db=Depends(get_db), user=Depends(current_user)
):
    return set_task_disposition(db, own_space(db, user.id, space_id), task_id, "skipped", utcnow())


@router.post(SPACE + "/tasks/{task_id}/postpone", response_model=DailyTaskResponse)
async def postpone(
    space_id: str, task_id: str, body: IdempotentRequest, db=Depends(get_db), user=Depends(current_user)
):
    return set_task_disposition(db, own_space(db, user.id, space_id), task_id, "postponed", utcnow())


@router.get(SPACE + "/suggestions", response_model=list[SuggestionResponse])
async def suggestions(space_id: str, db=Depends(get_db), user=Depends(current_user)):
    own_space(db, user.id, space_id)
    return [
        suggestion_view(row)
        for row in db.scalars(
            select(LearningSuggestion)
            .where(LearningSuggestion.space_id == space_id)
            .order_by(LearningSuggestion.created_at.desc())
            .limit(100)
        )
    ]


@router.post(SPACE + "/suggestions/{suggestion_id}/{decision}", response_model=SuggestionResponse)
async def decide(
    space_id: str,
    suggestion_id: str,
    decision: str,
    body: IdempotentRequest,
    db=Depends(get_db),
    user=Depends(current_user),
):
    from app.providers.base import ProviderError

    if decision not in {"accept", "skip"}:
        raise ProviderError("invalid_decision", "只支持接受或跳过建议", 422)
    return apply_suggestion(db, own_space(db, user.id, space_id), suggestion_id, decision, utcnow())


@router.get("/inbox", response_model=Page[InboxResponse])
async def messages(
    cursor: str | None = Query(None, max_length=1000),
    limit: int = Query(30, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(current_user),
):
    return list_inbox(db, user.id, cursor, limit)


@router.get("/inbox/unread-count", response_model=UnreadCountResponse)
async def unread(db=Depends(get_db), user=Depends(current_user)):
    from sqlalchemy import func

    return {
        "count": db.scalar(
            select(func.count())
            .select_from(InboxMessage)
            .where(InboxMessage.user_id == user.id, InboxMessage.read_at.is_(None))
        )
    }


@router.post("/inbox/{message_id}/read", response_model=InboxResponse)
async def read(message_id: str, body: IdempotentRequest, db=Depends(get_db), user=Depends(current_user)):
    return read_message(db, user.id, message_id, utcnow())


@router.get("/activity-jobs", response_model=Page[ActivityJobResponse])
async def activity_jobs(
    cursor: str | None = Query(None, max_length=1000),
    limit: int = Query(30, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(current_user),
):
    return owned_page(db, PeriodicJob, user.id, job_view, cursor, limit)


@router.post("/activity-jobs/{job_id}/retry", response_model=ActivityJobResponse)
async def retry(job_id: str, body: IdempotentRequest, db=Depends(get_db), user=Depends(current_user)):
    return retry_activity_job(db, user.id, job_id, utcnow())


@router.get(SPACE + "/weekly-summaries", response_model=Page[WeeklySummaryResponse])
async def weeks(
    space_id: str,
    cursor: str | None = Query(None, max_length=1000),
    limit: int = Query(30, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(current_user),
):
    from app.activity.weekly import summary_view
    from app.db.models import WeeklySummary

    own_space(db, user.id, space_id)
    return owned_page(db, WeeklySummary, user.id, summary_view, cursor, limit, space_id=space_id)


@router.get(SPACE + "/weekly-summaries/current", response_model=WeeklySummaryResponse)
async def week_preview(space_id: str, db=Depends(get_db), user=Depends(current_user)):
    from starlette.concurrency import run_in_threadpool

    from app.activity.calendar import current_week
    from app.activity.snapshot import read_snapshot
    from app.activity.weekly import summarize_week

    space = own_space(db, user.id, space_id)
    now = utcnow()
    snapshot = read_snapshot(db, space, now)
    return await run_in_threadpool(summarize_week, snapshot, current_week(now, user.timezone))


@router.post(SPACE + "/weekly-summaries/refresh", response_model=WeeklySummaryResponse)
async def refresh_week(space_id: str, request: Request, body: IdempotentRequest):
    from app.activity.calendar import previous_week
    from app.activity.weekly import publish_week
    from app.api.deps import session_user

    def run(factory):
        now = utcnow()
        with factory() as db:
            user = session_user(db, token_hash(request.cookies.get("study_session", "")))
            own_space(db, user.id, space_id)
            uid, tz = user.id, user.timezone
        return publish_week(factory, uid, space_id, previous_week(now, tz), now)

    return await activity_db(request.app, run)


@router.get(SPACE + "/weekly-summaries/{summary_id}", response_model=WeeklySummaryResponse)
async def week_detail(space_id: str, summary_id: str, db=Depends(get_db), user=Depends(current_user)):
    from app.activity.weekly import summary_view
    from app.db.models import WeeklySummary
    from app.providers.base import ProviderError

    own_space(db, user.id, space_id)
    row = db.scalar(
        select(WeeklySummary).where(
            WeeklySummary.id == summary_id,
            WeeklySummary.space_id == space_id,
            WeeklySummary.user_id == user.id,
        )
    )
    if not row:
        raise ProviderError("not_found", "周报不存在", 404)
    return summary_view(row)
