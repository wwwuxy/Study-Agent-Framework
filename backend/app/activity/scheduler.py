from sqlalchemy import select

from app.activity.calendar import local_day, previous_week
from app.activity.queue import lock_space
from app.db.models import PeriodicJob, StudySpace, as_utc


def enqueue_cycles(session_factory, now):
    with session_factory() as db:
        targets = [
            (s.user_id, s.id)
            for s in db.scalars(
                select(StudySpace)
                .where(StudySpace.status == "ready")
                .order_by(StudySpace.user_id, StudySpace.id)
            )
        ]
    created = 0
    for uid, sid in targets:
        with session_factory.begin() as db:
            from app.providers.base import ProviderError

            try:
                user, space = lock_space(db, uid, sid)
            except ProviderError:
                continue
            for kind, period in [
                ("daily_coordinate", local_day(now, user.timezone)),
                ("weekly_summary", previous_week(now, user.timezone)),
            ]:
                job = db.scalar(
                    select(PeriodicJob)
                    .where(
                        PeriodicJob.space_id == sid,
                        PeriodicJob.kind == kind,
                        PeriodicJob.period_key == period.key,
                    )
                    .with_for_update()
                )
                if not job:
                    db.add(
                        PeriodicJob(
                            user_id=uid,
                            space_id=space.id,
                            kind=kind,
                            period_key=period.key,
                            available_at=now,
                            data={
                                "timezone": period.timezone,
                                "start": period.start.isoformat(),
                                "end": period.end.isoformat(),
                            },
                        )
                    )
                    created += 1
                elif (
                    kind == "daily_coordinate"
                    and job.status == "succeeded"
                    and as_utc(job.available_at) <= now
                ):
                    job.status, job.attempts = "queued", 0
                    job.generation += 1
            # Superseded calendar jobs must not catch up all missed dates/weeks.
            for job in db.scalars(
                select(PeriodicJob).where(
                    PeriodicJob.space_id == sid, PeriodicJob.status.in_(["queued", "retry_wait", "running"])
                )
            ):
                active_key = (
                    local_day(now, user.timezone).key
                    if job.kind == "daily_coordinate"
                    else previous_week(now, user.timezone).key
                )
                if job.period_key != active_key:
                    job.status, job.lease_token = "cancelled", None
    return created
