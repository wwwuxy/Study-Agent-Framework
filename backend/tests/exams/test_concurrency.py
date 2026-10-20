from datetime import timedelta

from app.db.models import utcnow
from app.exam_diagnostics.queue import claim

from .test_uploads import create, put


def test_expired_claim_is_fenced(exam_env, pdf_bytes):
    row = create(exam_env, pdf_bytes)
    put(exam_env, row, pdf_bytes)
    exam_env.client.post(
        exam_env.root + "/" + row["id"] + "/start", json={"consent": True, "idempotency_key": "s"}
    )
    first = claim(exam_env.app.state.session_factory, utcnow())
    assert first is not None
    assert claim(exam_env.app.state.session_factory, utcnow()) is None
    second = claim(exam_env.app.state.session_factory, utcnow() + timedelta(seconds=181))
    assert second is not None and first.token != second.token


def test_exhausted_upload_claim_schedules_remote_cleanup(exam_env, pdf_bytes):
    from sqlalchemy import select

    from app.exam_diagnostics.models import ExamJob

    row = create(exam_env, pdf_bytes)
    put(exam_env, row, pdf_bytes)
    exam_env.client.post(
        exam_env.root + "/" + row["id"] + "/start", json={"consent": True, "idempotency_key": "s"}
    )
    first = claim(exam_env.app.state.session_factory, utcnow())
    with exam_env.app.state.session_factory.begin() as db:
        job = db.get(ExamJob, first.job_id)
        job.attempts = 3
        job.lease_until = utcnow() - timedelta(seconds=1)
        job.data = {**job.data, "remote_files": [{"ref": "remote-owned"}]}
    claim(exam_env.app.state.session_factory, utcnow())
    with exam_env.app.state.session_factory() as db:
        assert (
            db.scalar(select(ExamJob.id).where(ExamJob.kind == "cleanup", ExamJob.diagnostic_id == row["id"]))
            is not None
        )


def test_publication_acquires_owner_locks_before_job(exam_env, recognition_payload, pdf_bytes):
    from sqlalchemy import event
    from sqlalchemy.dialects import postgresql

    from app.core.orchestrator import concept_data, digest
    from app.exam_diagnostics.models import ExamJob
    from app.exam_diagnostics.worker import publish_result
    from app.schemas.exams import ExamAdvice

    from .test_publication import prepared

    claim_value, rec = prepared(exam_env, recognition_payload, pdf_bytes)
    with exam_env.app.state.session_factory.begin() as db:
        job = db.get(ExamJob, claim_value.job_id)
        job.data = {**job.data, "concept_fingerprint": digest(concept_data(db, exam_env.space_id))}
    acquired = []

    def capture(conn, clause, multiparams, params, options):
        sql = str(clause.compile(dialect=postgresql.dialect()))
        if "FOR UPDATE" in sql:
            for table in ("users", "study_spaces", "exam_diagnostics", "exam_jobs"):
                if "FROM " + table in sql:
                    acquired.append(table)
                    break

    event.listen(exam_env.app.state.engine, "before_execute", capture)
    try:
        publish_result(exam_env.app.state.session_factory, claim_value, rec, ExamAdvice(summary="test"))
    finally:
        event.remove(exam_env.app.state.engine, "before_execute", capture)
    assert acquired.index("users") < acquired.index("exam_jobs")
    assert acquired.index("study_spaces") < acquired.index("exam_jobs")
    assert acquired.index("exam_diagnostics") < acquired.index("exam_jobs")


def test_postgres_publish_and_cancel_finish_without_deadlock(exam_env, recognition_payload, pdf_bytes):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import pytest

    from app.core.orchestrator import concept_data, digest
    from app.db.models import StudySpace, User
    from app.exam_diagnostics.models import ExamJob
    from app.exam_diagnostics.queue import cancel
    from app.exam_diagnostics.worker import publish_result
    from app.providers.base import ProviderError
    from app.schemas.exams import ExamAdvice

    from .test_publication import prepared

    if exam_env.app.state.engine.dialect.name != "postgresql":
        pytest.skip("requires dedicated TEST_DATABASE_URL PostgreSQL database")
    claim_value, rec = prepared(exam_env, recognition_payload, pdf_bytes)
    sessions = exam_env.app.state.session_factory
    with sessions.begin() as db:
        job = db.get(ExamJob, claim_value.job_id)
        job.data = {**job.data, "concept_fingerprint": digest(concept_data(db, exam_env.space_id))}
    barrier = threading.Barrier(2)

    def publish_now():
        barrier.wait(timeout=5)
        try:
            return publish_result(sessions, claim_value, rec, ExamAdvice(summary="test")).status
        except ProviderError as error:
            assert error.code == "stale_exam_job"
            return "conflict"

    def cancel_now():
        barrier.wait(timeout=5)
        try:
            with sessions.begin() as db:
                return cancel(
                    db,
                    db.get(User, claim_value.user_id),
                    db.get(StudySpace, claim_value.space_id),
                    claim_value.diagnostic_id,
                ).status
        except ProviderError as error:
            assert error.code == "exam_already_published"
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(publish_now)
        second = pool.submit(cancel_now)
        results = [first.result(timeout=15), second.result(timeout=15)]
    assert "conflict" in results
    assert "completed" in results or "cancelled" in results
