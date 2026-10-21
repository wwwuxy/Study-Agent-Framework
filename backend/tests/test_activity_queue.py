from datetime import UTC, datetime, timedelta

from conftest import provider, register, space


def test_calendar_boundaries_dst_and_invalid_timezone():
    from app.activity.calendar import local_day, previous_week

    now = datetime(2026, 10, 19, 16, tzinfo=UTC)
    day = local_day(now, "Asia/Shanghai")
    assert day.key == "2026-10-20"
    assert day.start == now
    assert day.end == now + timedelta(days=1)
    week = previous_week(datetime(2026, 3, 9, 12, tzinfo=UTC), "America/New_York")
    assert week.start == datetime(2026, 3, 2, 5, tzinfo=UTC)
    assert week.end == datetime(2026, 3, 9, 4, tzinfo=UTC)
    assert local_day(now, "Bad/Zone").timezone == "Asia/Shanghai"
    assert local_day(now, "Bad/Zone").warning


def test_cycle_enqueue_is_bounded_and_timezone_change_does_not_duplicate(client):
    from sqlalchemy import select

    from app.activity.scheduler import enqueue_cycles
    from app.db.models import PeriodicJob, User

    register(client)
    space(client, provider(client))
    factory = client.app.state.session_factory
    now = datetime(2026, 10, 19, 1, tzinfo=UTC)
    assert enqueue_cycles(factory, now) == 2
    assert enqueue_cycles(factory, now + timedelta(minutes=1)) == 0
    with factory.begin() as db:
        db.scalar(select(User)).timezone = "UTC"
    assert enqueue_cycles(factory, now + timedelta(minutes=2)) == 0
    with factory() as db:
        assert len(list(db.scalars(select(PeriodicJob)))) == 2


def test_expired_lease_cannot_publish_after_second_worker_claim(client):
    from app.activity.queue import claim_job, finish_job
    from app.activity.scheduler import enqueue_cycles
    from app.providers.base import ProviderError

    register(client)
    space(client, provider(client))
    factory = client.app.state.session_factory
    now = datetime(2026, 10, 19, tzinfo=UTC)
    enqueue_cycles(factory, now)
    a = claim_job(factory, now)
    b = claim_job(factory, now + timedelta(seconds=181))
    assert a.job_id == b.job_id
    assert not finish_job(factory, a, now + timedelta(seconds=182), None)
    assert finish_job(factory, b, now + timedelta(seconds=182), ProviderError("bad", "fail"))
    # Other queued weekly work is independent of the retry delay.
    c = claim_job(factory, now + timedelta(seconds=200))
    assert c.job_id != b.job_id


def test_dead_letter_requires_explicit_retry(client):
    from app.activity.queue import claim_job, finish_job, retry_activity_job
    from app.activity.scheduler import enqueue_cycles
    from app.db.models import PeriodicJob
    from app.providers.base import ProviderError

    register(client)
    sid = space(client, provider(client))
    factory = client.app.state.session_factory
    now = datetime(2026, 10, 19, tzinfo=UTC)
    enqueue_cycles(factory, now)
    with factory.begin() as db:
        from sqlalchemy import delete

        db.execute(delete(PeriodicJob).where(PeriodicJob.kind == "weekly_summary"))
    for seconds in (0, 31, 152):
        claim = claim_job(factory, now + timedelta(seconds=seconds))
        assert claim.space_id == sid
        finish_job(factory, claim, now + timedelta(seconds=seconds), ProviderError("bad", "fail"))
    assert claim_job(factory, now + timedelta(days=1)) is None
    with factory.begin() as db:
        job = db.get(PeriodicJob, claim.job_id)
        assert job.status == "dead_letter"
        retry_activity_job(db, job.user_id, job.id, now + timedelta(days=1))
    assert claim_job(factory, now + timedelta(days=1))
