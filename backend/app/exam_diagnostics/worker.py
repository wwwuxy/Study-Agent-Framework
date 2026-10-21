"""Remote calls run outside DB transactions and the app's SQLite write lock."""

import asyncio
import base64
import logging
import time
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import urlsplit

from sqlalchemy import select

from app.chat.service import db_phase
from app.core.orchestrator import concept_data, digest, get_adapter
from app.db.models import AgentRun, StudySpace, new_id, utcnow
from app.exam_diagnostics import cleanup, publication, queries, queue, recognition
from app.exam_diagnostics.contracts import ExamCheckpoint
from app.exam_diagnostics.models import ExamAttachment, ExamJob
from app.exam_diagnostics.storage import ExamStorage
from app.providers.base import ExamInput, ModelCallLimits, ProviderError
from app.providers.compatible import CompatibleAdapter
from app.schemas.exams import ExamAdvice, ExamRecognition

logger = logging.getLogger("uvicorn.error.study_agent")


def prepare(sessions, claim):
    with sessions.begin() as db:
        space = db.get(StudySpace, claim.space_id)
        row, job = publication.guard(db, space, claim, utcnow())
        concepts = concept_data(db, space.id)
        if digest(concepts) != job.data["concept_fingerprint"]:
            raise ProviderError("exam_context_changed", "知识目录已变化，请重试识别", 409)
        job.lease_until = utcnow() + timedelta(seconds=180)
        attachments = db.scalars(
            select(ExamAttachment)
            .where(ExamAttachment.diagnostic_id == row.id)
            .order_by(ExamAttachment.position)
        ).all()
        return (
            dict(job.data),
            [{k: getattr(a, k) for k in ("id", "client_id", "mime_type")} for a in attachments],
            concepts,
        )


def uploading(sessions, claim):
    with sessions.begin() as db:
        job = queue.guard(db, claim, utcnow())
        job.data = {**job.data, "uploading": True}
        job.lease_until = utcnow() + timedelta(seconds=180)


def release_upload(sessions, claim):
    with sessions.begin() as db:
        queries.lock_diagnostic(db, claim.user_id, claim.space_id, claim.diagnostic_id, allow_deleted=True)
        job = db.scalar(select(ExamJob).where(ExamJob.id == claim.job_id).with_for_update())
        if job and job.lease_token == claim.token:
            job.data = {**job.data, "uploading": False}
            if job.status == "cancelled":
                job.lease_token = None
                job.lease_until = None
            queue.enqueue_cleanup(db, job)


def audit(sessions, claim, snapshot, step, usage, error=None, *, elapsed_ms=0):
    with sessions.begin() as db:
        space = db.get(StudySpace, claim.space_id)
        if not space or space.status == "deleted":
            return
        # No document, prompt, credential or raw remote response enters this record.
        db.add(
            AgentRun(
                id=new_id(),
                user_id=claim.user_id,
                space_id=claim.space_id,
                provider_id=snapshot["id"],
                model=snapshot["chat_model"],
                step=step,
                elapsed_ms=elapsed_ms,
                usage=dict(usage),
                error_code=error.code if error else None,
            )
        )


def fail(sessions, claim, error):
    with sessions.begin() as db:
        queries.lock_diagnostic(db, claim.user_id, claim.space_id, claim.diagnostic_id, allow_deleted=True)
        job = db.scalar(select(ExamJob).where(ExamJob.id == claim.job_id).with_for_update())
        if not job:
            return
        if job.lease_token == claim.token:
            if job.status == "running":
                job.status = "failed"
                job.active_space_id = None
                job.error_code = error.code
                job.error_message = error.message[:500]
                if job.kind == "recognize":
                    from app.exam_diagnostics.models import ExamDiagnostic

                    row = db.get(ExamDiagnostic, claim.diagnostic_id)
                    if row and row.status not in {"deleted", "cancelled"}:
                        row.status = "failed"
            job.data = {**job.data, "uploading": False}
            job.lease_token = None
            job.lease_until = None
        if job.kind == "recognize":
            queue.enqueue_cleanup(db, job)


def publish_result(sessions, claim, rec, advice):
    with sessions.begin() as db:
        space = db.get(StudySpace, claim.space_id)
        # Recheck graph and provider with the same transaction that publishes.
        _, job = publication.guard(db, space, claim, utcnow())
        if digest(concept_data(db, claim.space_id)) != job.data["concept_fingerprint"]:
            raise ProviderError("exam_context_changed", "知识目录已变化，尚未更新状态", 409)
        result = asyncio.run(publication.publish(db, space, claim, rec, advice, now=utcnow()))
        queue.enqueue_cleanup(db, job)
        if not job.data.get("remote_files"):
            data = dict(job.data)
            data.pop("provider_snapshot", None)
            job.data = data
        return result


async def run_claim(app, claim):
    snapshot = None
    adapter = None
    started = time.monotonic()
    phase = "试卷识别"
    try:

        def kind(sessions):
            with sessions() as db:
                return db.get(ExamJob, claim.job_id).kind

        if await db_phase(app, kind, write=False) == "cleanup":
            await asyncio.wait_for(
                cleanup.run(app, claim), timeout=app.state.settings.exam_call_timeout_seconds
            )
            return
        data, attachments, concepts = await db_phase(app, prepare, claim)
        snapshot = data["provider_snapshot"]
        limits = ModelCallLimits(app.state.settings.exam_max_output_tokens, 0)
        adapter = get_adapter(SimpleNamespace(app=app), SimpleNamespace(**snapshot), call_limits=limits)
        if isinstance(adapter, CompatibleAdapter):
            # The stage budget must reach the HTTP client; otherwise its default
            # 30-second read timeout fires before the 120-second exam deadline.
            adapter.timeout = app.state.settings.exam_call_timeout_seconds
            if urlsplit(adapter.base_url).hostname == "api.deepseek.com" and adapter.model in {
                "deepseek-flash",
                "deepseek-v4-flash",
                "deepseek-v4-flash-vision-exp",
            }:
                adapter.thinking_mode = "disabled"
        rec = ExamRecognition.model_validate(data["recognition"]) if data.get("recognition") else None
        advice = ExamAdvice.model_validate(data["advice"]) if data.get("advice") else None

        async def remote(operation):
            app.state.limiter.check("model:" + claim.user_id, app.state.settings.provider_calls_per_minute)
            return await asyncio.wait_for(operation, timeout=app.state.settings.exam_call_timeout_seconds)

        if rec is None:
            inputs = []
            storage = ExamStorage(app.state.settings.material_storage_dir)
            for attachment in attachments:
                if attachment["mime_type"] == "application/pdf":
                    await db_phase(app, uploading, claim)
                    with storage.open(claim.user_id, claim.space_id, attachment["id"]) as handle:
                        ref = await remote(adapter.upload_file(handle, "exam.pdf"))
                    await cleanup.cleanup_db(
                        app,
                        cleanup.register_remote,
                        claim,
                        snapshot["id"],
                        ref,
                        provider_snapshot=snapshot,
                        maintenance=True,
                    )
                    inputs.append(ExamInput(attachment["client_id"], "application/pdf", file_ref=ref))
                else:
                    raw = await asyncio.to_thread(
                        storage.read, claim.user_id, claim.space_id, attachment["id"]
                    )
                    inputs.append(
                        ExamInput(
                            attachment["client_id"],
                            attachment["mime_type"],
                            data_url="data:"
                            + attachment["mime_type"]
                            + ";base64,"
                            + base64.b64encode(raw).decode(),
                        )
                    )
            # Each model stage rechecks the live binding before sending user content.
            await db_phase(app, prepare, claim)
            task = recognition.build_task(
                [a["client_id"] for a in attachments], concepts, app.state.settings.exam_max_questions
            )
            rec = await remote(recognition.recognize(adapter, inputs, task, limits))
            await db_phase(
                app,
                queue.checkpoint,
                claim,
                "analyzing",
                ExamCheckpoint(rec, None, data["provider_fingerprint"], data["concept_fingerprint"]),
            )
        if advice is None:
            phase = "诊断建议生成"
            await db_phase(app, prepare, claim)
            advice = await remote(recognition.advise(adapter, rec, concepts, limits))
            await db_phase(
                app,
                queue.checkpoint,
                claim,
                "publishing",
                ExamCheckpoint(rec, advice, data["provider_fingerprint"], data["concept_fingerprint"]),
            )
        await db_phase(
            app,
            audit,
            claim,
            snapshot,
            "exam_diagnostic",
            adapter.usage,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )
        await db_phase(app, publish_result, claim, rec, advice)
    except asyncio.CancelledError:
        # Leave a leased checkpoint so another worker can recover after expiry.
        raise
    except Exception as exc:
        error = (
            exc
            if isinstance(exc, ProviderError)
            else ProviderError(
                "exam_timeout" if isinstance(exc, TimeoutError) else "exam_processing_failed",
                "试卷处理未完成，可稍后重试",
            )
        )
        if error.code in {"provider_timeout", "exam_timeout"}:
            error = ProviderError(
                error.code,
                f"{phase}请求超时（上限 {app.state.settings.exam_call_timeout_seconds} 秒）；"
                "可重试，已完成的处理阶段会保留。",
            )
        logger.info("exam_failed code=%s type=%s", error.code, type(exc).__name__)
        try:
            if snapshot and adapter:
                await db_phase(
                    app,
                    audit,
                    claim,
                    snapshot,
                    "exam_diagnostic",
                    adapter.usage,
                    error,
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                )
            await db_phase(app, fail, claim, error)
        except ProviderError as bookkeeping_error:
            if bookkeeping_error.code != "maintenance":
                raise
            # Lease recovery resumes normal work after maintenance. Remote handles
            # have already been saved through the narrowly scoped cleanup path.

    finally:
        # A cancelled user job may have returned a late remote handle above.
        try:
            await cleanup.cleanup_db(app, release_upload, claim, maintenance=True)
        except ProviderError:
            pass


async def tick(app):
    count = 0
    for _ in range(5):
        claim = await db_phase(app, queue.claim, utcnow(), app.state.settings.exam_job_attempts)
        if claim is None:
            break
        await run_claim(app, claim)
        count += 1
    return count


async def worker(app):
    while True:
        try:
            await tick(app)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.info("exam_worker_deferred type=%s", type(exc).__name__)
        await asyncio.sleep(2)
