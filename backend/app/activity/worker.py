"""Durable local statistics only: this module never imports a model provider."""

import asyncio
import logging
from datetime import datetime

from app.activity.contracts import CalendarPeriod
from app.activity.daily import coordinate_day
from app.activity.db_phase import activity_db
from app.activity.queue import claim_job, finish_job, guard_claim, lock_space
from app.activity.scheduler import enqueue_cycles
from app.activity.weekly import publish_week
from app.db.models import utcnow
from app.providers.base import ProviderError

logger = logging.getLogger("uvicorn.error.study_agent")


def execute_claim(factory, claim, now):
    with factory.begin() as db:
        lock_space(db, claim.user_id, claim.space_id)
        job = guard_claim(db, claim, now)
        period = CalendarPeriod(
            job.period_key,
            job.data["timezone"],
            datetime.fromisoformat(job.data["start"]),
            datetime.fromisoformat(job.data["end"]),
        )
    if claim.kind == "daily_coordinate":
        return coordinate_day(factory, claim.user_id, claim.space_id, now, claim=claim)
    if claim.kind == "weekly_summary":
        return publish_week(factory, claim.user_id, claim.space_id, period, now, claim=claim)
    raise ProviderError("unknown_job", "未识别的后台任务类型", 422)


async def tick(app):
    await activity_db(app, enqueue_cycles, utcnow())
    # Bound a sweep so shutdown and HTTP traffic are never starved by a large queue.
    for _ in range(20):
        claim = await activity_db(app, claim_job, utcnow())
        if not claim:
            break
        error = None
        try:
            await activity_db(app, execute_claim, claim, utcnow())
        except ProviderError as exc:
            if exc.code == "maintenance":
                raise
            error = exc
        except Exception as exc:
            logger.error("activity_job_failed kind=%s type=%s", claim.kind, type(exc).__name__)
            error = ProviderError("activity_failed", "后台统计未完成，请稍后重试")
        await activity_db(app, finish_job, claim, utcnow(), error)


async def worker(app):
    while True:
        try:
            await tick(app)
        except ProviderError as exc:
            logger.info("activity_tick_deferred code=%s", exc.code)
        except Exception as exc:
            logger.error("activity_tick_failed type=%s", type(exc).__name__)
        await asyncio.sleep(app.state.settings.m4_tick_seconds)
