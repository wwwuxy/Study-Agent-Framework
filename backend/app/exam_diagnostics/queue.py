"""Durable claims, fenced checkpoints, and idempotent user actions."""

from dataclasses import asdict
from datetime import timedelta

from sqlalchemy import and_, or_, select, update

from app.api.deps import own_provider
from app.chat.context import snapshot_provider
from app.core.orchestrator import concept_data, digest
from app.db.models import as_utc, new_id, utcnow
from app.exam_diagnostics import queries
from app.exam_diagnostics.contracts import ExamClaim
from app.exam_diagnostics.models import ExamAttachment, ExamDiagnostic, ExamJob
from app.exam_diagnostics.storage import ExamStorage
from app.knowledge.materials import fingerprint
from app.providers.base import ProviderError


def guard(db, claim, now):
    queries.lock_diagnostic(db, claim.user_id, claim.space_id, claim.diagnostic_id, allow_deleted=True)
    job = db.scalar(
        select(ExamJob)
        .where(ExamJob.id == claim.job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        not job
        or job.status != "running"
        or job.lease_token != claim.token
        or job.generation != claim.generation
        or not job.lease_until
        or as_utc(job.lease_until) <= now
    ):
        raise ProviderError("stale_exam_job", "试卷任务已过期或已取消", 409)
    return job


def start(db, user, space, diagnostic_id, body, settings):
    row = queries.own(db, user.id, space.id, diagnostic_id, lock=True)
    previous = db.scalar(
        select(ExamJob).where(
            ExamJob.diagnostic_id == row.id,
            ExamJob.request_key == body.idempotency_key,
            ExamJob.kind == "recognize",
        )
    )
    hashed = digest(body.model_dump())
    if previous:
        if previous.request_digest != hashed:
            raise ProviderError("idempotency_conflict", "同一开始请求键不能用于不同授权", 409)
        return queries.detail(db, user.id, space.id, row.id)
    if row.status == "completed":
        return queries.detail(db, user.id, space.id, row.id)
    if row.status != "draft":
        raise ProviderError("exam_not_draft", "试卷已开始处理，请查看进度或重试", 409)
    if not body.consent:
        raise ProviderError("file_consent_required", "本次识别须同意将试卷交给所选远端模型处理", 422)
    attachments = db.scalars(
        select(ExamAttachment).where(ExamAttachment.diagnostic_id == row.id).order_by(ExamAttachment.position)
    ).all()
    if not attachments or not all(a.received for a in attachments):
        raise ProviderError("exam_upload_incomplete", "附件尚未全部上传", 409)
    canonical = digest(sorted((a.sha256, a.size_bytes, a.mime_type) for a in attachments))
    existing = db.scalar(
        select(ExamDiagnostic).where(
            ExamDiagnostic.space_id == space.id,
            ExamDiagnostic.verified_files_digest == canonical,
            ExamDiagnostic.id != row.id,
        )
    )
    if existing:
        row.status = "duplicate"
        row.canonical_id = existing.id
        storage = ExamStorage(settings.material_storage_dir)
        for a in attachments:
            storage.delete(user.id, space.id, a.id)
            a.received = False
        db.flush()
        return queries.detail(db, user.id, space.id, existing.id)
    if db.scalar(select(ExamJob.id).where(ExamJob.active_space_id == space.id)):
        raise ProviderError("exam_busy", "该空间已有试卷正在处理，请稍后再试", 409)
    config = own_provider(db, user.id, space.provider_id, True)
    for a in attachments:
        supported = (
            (
                config.capabilities.get("file_input")
                and a.mime_type in config.capabilities.get("supported_mime_types", [])
            )
            if a.mime_type == "application/pdf"
            else (
                config.capabilities.get("image_input")
                and a.mime_type in config.capabilities.get("supported_image_mime_types", [])
            )
        )
        if not supported:
            raise ProviderError("capability_not_supported", "请先检测当前模型对应的 PDF／图片理解能力", 422)
    row.verified_files_digest = canonical
    row.status = "queued"
    row.data = {**row.data, "is_demo": bool(config.capabilities.get("is_demo"))}
    job = ExamJob(
        id=new_id(),
        user_id=user.id,
        space_id=space.id,
        diagnostic_id=row.id,
        request_key=body.idempotency_key,
        request_digest=hashed,
        active_space_id=space.id,
        generation=row.generation,
        provider_id=config.id,
        data={
            "provider_fingerprint": fingerprint(config),
            "provider_snapshot": asdict(snapshot_provider(config)),
            "concept_fingerprint": digest(concept_data(db, space.id)),
            "remote_files": [],
        },
    )
    db.add(job)
    db.flush()
    return queries.detail(db, user.id, space.id, row.id)


def claim(sessions, now, max_attempts=3):
    with sessions.begin() as db:
        job = db.scalar(
            select(ExamJob)
            .where(
                or_(ExamJob.status == "queued", and_(ExamJob.status == "running", ExamJob.lease_until <= now))
            )
            .order_by(ExamJob.created_at, ExamJob.id)
            .limit(1)
        )
        if not job:
            return None
        # Candidate selection is unlocked. Acquire ownership before any job lock,
        # then revalidate: a concurrent worker or cancel may have changed it.
        queries.lock_diagnostic(db, job.user_id, job.space_id, job.diagnostic_id, allow_deleted=True)
        job = db.scalar(
            select(ExamJob)
            .where(ExamJob.id == job.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not job or not (
            job.status == "queued"
            or (job.status == "running" and job.lease_until and as_utc(job.lease_until) <= now)
        ):
            return None
        if job.attempts >= max_attempts:
            job.status = "failed"
            job.active_space_id = None
            job.error_code = "lease_exhausted"
            job.error_message = "多次处理中断，请手动重试"
            if job.kind == "recognize":
                row = db.get(ExamDiagnostic, job.diagnostic_id)
                if row and row.status not in {"deleted", "cancelled"}:
                    row.status = "failed"
                enqueue_cleanup(db, job)
            job.lease_token = None
            job.lease_until = None
            return None
        old_token = job.lease_token
        token = new_id()
        changed = db.execute(
            update(ExamJob)
            .where(ExamJob.id == job.id, ExamJob.lease_token == old_token, ExamJob.status == job.status)
            .values(
                status="running",
                lease_token=token,
                lease_until=now + timedelta(seconds=180),
                attempts=ExamJob.attempts + 1,
            )
            .execution_options(synchronize_session=False)
        )
        if changed.rowcount != 1:
            return None
        if job.kind == "recognize":
            row = db.get(ExamDiagnostic, job.diagnostic_id)
            if row and row.status not in {"cancelled", "deleted"}:
                row.status = "running"
        return ExamClaim(job.id, job.diagnostic_id, job.user_id, job.space_id, token, job.generation)


def checkpoint(sessions, claim, stage, checkpoint):
    with sessions.begin() as db:
        job = guard(db, claim, utcnow())
        job.stage = stage
        job.lease_until = utcnow() + timedelta(seconds=180)
        job.data = {
            **job.data,
            "recognition": checkpoint.recognition.model_dump() if checkpoint.recognition else None,
            "advice": checkpoint.advice.model_dump() if checkpoint.advice else None,
        }


def enqueue_cleanup(db, source):
    if not source.data.get("remote_files") and not source.data.get("uploading"):
        return
    key = "cleanup_" + source.id
    previous = db.scalar(
        select(ExamJob).where(ExamJob.diagnostic_id == source.diagnostic_id, ExamJob.request_key == key)
    )
    if previous:
        if previous.status != "running":
            previous.status = "queued"
            previous.attempts = 0
        return
    db.add(
        ExamJob(
            id=new_id(),
            user_id=source.user_id,
            space_id=source.space_id,
            diagnostic_id=source.diagnostic_id,
            request_key=key,
            kind="cleanup",
            generation=source.generation,
            data={"source_job_id": source.id},
        )
    )


def retry(db, user, space, diagnostic_id, body):
    row = queries.own(db, user.id, space.id, diagnostic_id, lock=True)
    actions = row.data.get("retry_actions", {})
    hashed = digest(body.model_dump())
    if body.idempotency_key in actions:
        if actions[body.idempotency_key] != hashed:
            raise ProviderError("idempotency_conflict", "重试键已用于不同请求", 409)
        return queries.detail(db, user.id, space.id, row.id)
    if row.status == "completed":
        for job in db.scalars(
            select(ExamJob).where(
                ExamJob.diagnostic_id == row.id, ExamJob.kind == "cleanup", ExamJob.status == "failed"
            )
        ):
            job.status = "queued"
            job.attempts = 0
        row.data = {**row.data, "retry_actions": {**actions, body.idempotency_key: hashed}}
        return queries.detail(db, user.id, space.id, row.id)
    job = db.scalar(
        select(ExamJob)
        .where(ExamJob.diagnostic_id == row.id, ExamJob.kind == "recognize")
        .order_by(ExamJob.created_at.desc())
    )
    if (
        not job
        or row.status not in {"failed", "cancelled", "running"}
        or (job.status == "running" and job.lease_until and as_utc(job.lease_until) > utcnow())
    ):
        raise ProviderError("exam_not_retryable", "只有失败、取消或已中断的试卷可重试", 409)
    if db.scalar(select(ExamJob.id).where(ExamJob.active_space_id == space.id, ExamJob.id != job.id)):
        raise ProviderError("exam_busy", "该空间已有试卷正在处理", 409)
    config = own_provider(db, user.id, space.provider_id, True)
    changed = config.id != job.provider_id or fingerprint(config) != job.data.get("provider_fingerprint")
    if changed and not body.consent:
        raise ProviderError("file_consent_required", "模型已变化，需要重新授权远端处理", 422)

    attachments = db.scalars(select(ExamAttachment).where(ExamAttachment.diagnostic_id == row.id)).all()
    if not all(a.received for a in attachments):
        raise ProviderError("file_unavailable", "试卷原文不可用", 422)
    for a in attachments:
        caps = config.capabilities
        supported = (
            (caps.get("file_input") and a.mime_type in caps.get("supported_mime_types", []))
            if a.mime_type == "application/pdf"
            else (caps.get("image_input") and a.mime_type in caps.get("supported_image_mime_types", []))
        )
        if not supported:
            raise ProviderError("capability_not_supported", "当前模型尚未验证试卷格式能力", 422)
    graph = digest(concept_data(db, space.id))
    data = dict(job.data)
    if changed or graph != data.get("concept_fingerprint"):
        data.pop("recognition", None)
        data.pop("advice", None)
    row.generation += 1
    row.status = "queued"
    row.data = {
        **row.data,
        "retry_actions": {**actions, body.idempotency_key: hashed},
        "is_demo": bool(config.capabilities.get("is_demo")),
    }
    job.generation = row.generation
    job.status = "queued"
    job.active_space_id = space.id
    job.lease_token = None
    job.lease_until = None
    job.attempts = 0
    job.error_code = None
    job.error_message = None
    job.provider_id = config.id
    job.data = {
        **data,
        "provider_snapshot": asdict(snapshot_provider(config)),
        "provider_fingerprint": fingerprint(config),
        "concept_fingerprint": graph,
    }
    db.flush()
    return queries.detail(db, user.id, space.id, row.id)


def cancel(db, user, space, diagnostic_id):
    row = queries.own(db, user.id, space.id, diagnostic_id, lock=True)
    if row.status == "completed":
        raise ProviderError("exam_already_published", "已生效诊断不能通过取消撤回证据", 409)
    if row.status == "cancelled":
        return queries.detail(db, user.id, space.id, row.id)
    row.generation += 1
    row.status = "cancelled"
    for job in db.scalars(
        select(ExamJob).where(ExamJob.diagnostic_id == row.id, ExamJob.kind == "recognize")
    ):
        job.status = "cancelled"
        job.active_space_id = None
        enqueue_cleanup(db, job)
    db.flush()
    return queries.detail(db, user.id, space.id, row.id)
