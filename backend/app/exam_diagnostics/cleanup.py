from types import SimpleNamespace

from sqlalchemy import delete, select

from app.chat.service import db_phase
from app.core.orchestrator import get_adapter
from app.db.models import as_utc, utcnow
from app.exam_diagnostics import queries
from app.exam_diagnostics.models import ExamAttachment, ExamDiagnostic, ExamJob, ExamQuestion
from app.exam_diagnostics.queue import enqueue_cleanup, guard
from app.exam_diagnostics.storage import ExamStorage
from app.providers.base import ProviderError


def register_remote(sessions, claim, provider_id, ref, *, provider_snapshot):
    with sessions.begin() as db:
        queries.lock_diagnostic(db, claim.user_id, claim.space_id, claim.diagnostic_id, allow_deleted=True)
        job = db.scalar(select(ExamJob).where(ExamJob.id == claim.job_id).with_for_update())
        if not job:
            raise ProviderError("cleanup_registration_failed", "无法登记远端文件清理", 409)
        refs = list(job.data.get("remote_files", []))
        value = {"ref": ref, "provider_id": provider_id, "provider_snapshot": provider_snapshot}
        if value not in refs:
            refs.append(value)
        job.data = {**job.data, "remote_files": refs, "uploading": False}
        enqueue_cleanup(db, job)


def prepare(sessions, claim):
    with sessions.begin() as db:
        cleanup = guard(db, claim, utcnow())
        source = db.get(ExamJob, cleanup.data["source_job_id"])
        if source and (
            source.status in {"queued", "running"}
            or (source.data.get("uploading") and source.lease_until and as_utc(source.lease_until) > utcnow())
        ):
            cleanup.status = "queued"
            cleanup.attempts = max(0, cleanup.attempts - 1)
            cleanup.lease_token = None
            return None
        return list(source.data.get("remote_files", [])) if source else []


def acknowledge(sessions, claim, reference):
    with sessions.begin() as db:
        job = guard(db, claim, utcnow())
        source = db.scalar(select(ExamJob).where(ExamJob.id == job.data["source_job_id"]).with_for_update())
        if source:
            refs = [r for r in source.data.get("remote_files", []) if r != reference]
            source.data = {**source.data, "remote_files": refs}


def finish(sessions, claim):
    with sessions.begin() as db:
        job = guard(db, claim, utcnow())
        source = db.get(ExamJob, job.data["source_job_id"])
        if source and source.data.get("remote_files"):
            job.status = "queued"
        else:
            job.status = "succeeded"
            if source and not source.data.get("uploading"):
                data = dict(source.data)
                data.pop("provider_snapshot", None)
                source.data = data
        job.lease_token = None
        job.lease_until = None
        job.error_code = None
        job.error_message = None


async def cleanup_db(app, operation, *args, maintenance=False, **kwargs):
    if not maintenance:
        return await db_phase(app, operation, *args, **kwargs)
    # Local reset owns the maintenance marker; only remote-handle cleanup bypasses it.
    from starlette.concurrency import run_in_threadpool

    if app.state.settings.database_url.startswith("sqlite"):
        async with app.state.sqlite_lock:
            return await run_in_threadpool(operation, app.state.session_factory, *args, **kwargs)
    return await run_in_threadpool(operation, app.state.session_factory, *args, **kwargs)


async def run(app, claim, *, maintenance=False):
    refs = await cleanup_db(app, prepare, claim, maintenance=maintenance)
    if refs is None:
        return
    for entry in refs:
        adapter = get_adapter(SimpleNamespace(app=app), SimpleNamespace(**entry["provider_snapshot"]))
        await adapter.delete_file(entry["ref"])
        await cleanup_db(app, acknowledge, claim, entry, maintenance=maintenance)
    await cleanup_db(app, finish, claim, maintenance=maintenance)


def erase_space(db, space, storage_root):
    ExamStorage(storage_root).discard_space(space.user_id, space.id)
    diagnostics = db.scalars(select(ExamDiagnostic).where(ExamDiagnostic.space_id == space.id)).all()
    for row in diagnostics:
        row.status = "deleted"
        row.generation += 1
        row.name = ""
        row.exam_date = None
        row.data = {}
        row.request_digest = ""
        row.verified_files_digest = None
    for job in db.scalars(select(ExamJob).where(ExamJob.space_id == space.id, ExamJob.kind == "recognize")):
        job.status = "cancelled"
        job.active_space_id = None
        job.data = {
            k: v for k, v in job.data.items() if k in {"remote_files", "provider_snapshot", "uploading"}
        }
        job.error_code = None
        job.error_message = None
        enqueue_cleanup(db, job)
    db.execute(delete(ExamQuestion).where(ExamQuestion.space_id == space.id))
    db.execute(delete(ExamAttachment).where(ExamAttachment.space_id == space.id))


def purgeable(db, space_id):
    for job in db.scalars(select(ExamJob).where(ExamJob.space_id == space_id)):
        if job.data.get("remote_files") or (job.lease_until and as_utc(job.lease_until) > utcnow()):
            return False
        if job.kind == "cleanup" and job.status != "succeeded":
            return False
    return True


def purge(db, space_id):
    db.execute(delete(ExamJob).where(ExamJob.space_id == space_id))
    db.execute(delete(ExamDiagnostic).where(ExamDiagnostic.space_id == space_id))


async def maintenance_sweep(app, space_ids):
    from datetime import timedelta

    from app.db.models import new_id
    from app.exam_diagnostics.contracts import ExamClaim

    def targets(sessions):
        result = []
        with sessions.begin() as db:
            jobs = db.scalars(
                select(ExamJob).where(
                    ExamJob.space_id.in_(space_ids),
                    ExamJob.kind == "cleanup",
                    ExamJob.status.in_(["queued", "failed"]),
                )
            ).all()
            for job in jobs:
                job.status = "running"
                job.lease_token = new_id()
                job.lease_until = utcnow() + timedelta(seconds=180)
                result.append(
                    ExamClaim(
                        job.id, job.diagnostic_id, job.user_id, job.space_id, job.lease_token, job.generation
                    )
                )
        return result

    for claim in await cleanup_db(app, targets, maintenance=True):
        try:
            await run(app, claim, maintenance=True)
        except ProviderError as error:

            def failed(sessions, current_claim=claim, current_error=error):
                with sessions.begin() as db:
                    job = db.get(ExamJob, current_claim.job_id)
                    if job and job.lease_token == current_claim.token:
                        job.status = "failed"
                        job.lease_until = None
                        job.lease_token = None
                        job.error_code = current_error.code
                        job.error_message = current_error.message[:500]

            await cleanup_db(app, failed, maintenance=True)
