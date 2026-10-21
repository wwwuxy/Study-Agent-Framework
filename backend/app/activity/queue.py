from datetime import timedelta

from sqlalchemy import and_, or_, select

from app.activity.contracts import JobClaim
from app.db.models import PeriodicJob, StudySpace, User, as_utc, new_id
from app.providers.base import ProviderError
from app.schemas.activity import ActivityJobResponse


def job_view(row):
    return ActivityJobResponse(
        id=row.id,
        study_space_id=row.space_id,
        kind=row.kind,
        status=row.status,
        attempts=row.attempts,
        executions=row.executions,
        available_at=as_utc(row.available_at).isoformat(),
        error_code=row.error_code,
        error_message=row.error_message,
        created_at=as_utc(row.created_at).isoformat(),
    )


def claim_job(session_factory, now):
    with session_factory.begin() as db:
        job = db.scalar(
            select(PeriodicJob)
            .where(
                or_(
                    and_(PeriodicJob.status.in_(["queued", "retry_wait"]), PeriodicJob.available_at <= now),
                    and_(PeriodicJob.status == "running", PeriodicJob.lease_until <= now),
                )
            )
            .order_by(PeriodicJob.available_at, PeriodicJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return None
        # Expired claims consume an attempt too; a crashed job cannot retry forever.
        if job.attempts >= 3:
            job.status = "dead_letter"
            job.lease_token = None
            job.error_code, job.error_message = "lease_exhausted", "多次执行中断，请检查后手动重试"
            return None
        job.status, job.lease_token = "running", new_id()
        job.lease_until = now + timedelta(seconds=180)
        job.attempts += 1
        return JobClaim(
            job.id, job.lease_token, job.user_id, job.space_id, job.kind, job.period_key, job.generation
        )


def guard_claim(db, claim, now):
    row = db.scalar(
        select(PeriodicJob)
        .where(PeriodicJob.id == claim.job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        not row
        or row.status != "running"
        or row.lease_token != claim.token
        or row.generation != claim.generation
        or as_utc(row.lease_until) <= now
    ):
        raise ProviderError("stale_job", "任务已过期或已由其他进程处理", 409)
    return row


def lock_space(db, user_id, space_id):
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    space = db.scalar(
        select(StudySpace)
        .where(StudySpace.id == space_id, StudySpace.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not user or not space or space.status in {"deleted", "archived"}:
        raise ProviderError("not_found", "学习空间不存在", 404)
    return user, space


def finish_job(session_factory, claim, now, error=None):
    with session_factory.begin() as db:
        try:
            lock_space(db, claim.user_id, claim.space_id)
            job = guard_claim(db, claim, now)
        except ProviderError:
            return False
        job.lease_token, job.lease_until = None, None
        job.executions += 1
        if error:
            job.status = "dead_letter" if job.attempts >= 3 else "retry_wait"
            job.available_at = now + timedelta(seconds=30 if job.attempts == 1 else 120)
            job.error_code, job.error_message = error.code, error.message[:500]
        else:
            job.status = "succeeded"
            job.error_code, job.error_message = None, None
            job.available_at = now + timedelta(seconds=60)
        return True


def retry_activity_job(db, user_id, job_id, now):
    job = db.scalar(select(PeriodicJob).where(PeriodicJob.id == job_id, PeriodicJob.user_id == user_id))
    if not job:
        raise ProviderError("not_found", "后台任务不存在", 404)
    lock_space(db, user_id, job.space_id)
    job = db.scalar(
        select(PeriodicJob)
        .where(PeriodicJob.id == job_id, PeriodicJob.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not job:
        raise ProviderError("not_found", "后台任务不存在", 404)
    if job.status != "dead_letter":
        raise ProviderError("job_not_retryable", "仅失败终止的后台任务可重试", 409)
    job.status, job.attempts, job.available_at = "queued", 0, now
    job.generation += 1
    return job_view(job)
