from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select

from app.api.deps import session_user
from app.chat.service import db_phase
from app.core.orchestrator import digest
from app.db.models import new_id
from app.exam_diagnostics import queries
from app.exam_diagnostics.models import ExamAttachment, ExamDiagnostic
from app.exam_diagnostics.storage import ExamStorage
from app.providers.base import ProviderError
from app.schemas.exams import AttachmentManifest


def create_draft(db, user, space, body, settings):
    limit = min(settings.material_max_bytes, settings.exam_max_bytes)
    if (
        len(body.attachments) > settings.exam_max_images
        or any(a.size_bytes > limit for a in body.attachments)
        or sum(a.size_bytes for a in body.attachments) > 2 * limit
    ):
        raise ProviderError("file_too_large", "试卷文件大小或数量超过限制", 413)
    if body.exam_date and body.exam_date > datetime.now(ZoneInfo(user.timezone)).date():
        raise ProviderError("invalid_exam_date", "考试日期不能晚于今天", 422)
    fingerprint = digest(body.model_dump(mode="json", exclude={"idempotency_key"}))
    previous = db.scalar(
        select(ExamDiagnostic).where(
            ExamDiagnostic.space_id == space.id, ExamDiagnostic.request_key == body.idempotency_key
        )
    )
    if previous:
        if previous.request_digest != fingerprint:
            raise ProviderError("idempotency_conflict", "同一请求键不能创建不同试卷", 409)
        return queries.detail(db, user.id, space.id, previous.id)
    row = ExamDiagnostic(
        id=new_id(),
        user_id=user.id,
        space_id=space.id,
        request_key=body.idempotency_key,
        request_digest=fingerprint,
        name=body.name,
        exam_date=str(body.exam_date) if body.exam_date else None,
    )
    db.add(row)
    db.flush()
    for i, a in enumerate(body.attachments):
        db.add(
            ExamAttachment(
                id=new_id(),
                user_id=user.id,
                space_id=space.id,
                diagnostic_id=row.id,
                position=i,
                **a.model_dump(),
            )
        )
    db.flush()
    return queries.detail(db, user.id, space.id, row.id)


async def receive_attachment(app, session_hash, space_id, diagnostic_id, attachment_id, chunks, mime):
    def prepare(sessions):
        with sessions() as db:
            user = session_user(db, session_hash)
            row, a = queries.attachment(db, user.id, space_id, diagnostic_id, attachment_id)
            if row.status != "draft":
                raise ProviderError("exam_not_draft", "只有未开始的试卷可上传附件", 409)
            if mime != a.mime_type:
                raise ProviderError("unsupported_file_type", "附件格式与清单不一致", 422)
            return (
                user.id,
                row.generation,
                AttachmentManifest(**{k: getattr(a, k) for k in AttachmentManifest.model_fields}),
            )

    user_id, generation, manifest = await db_phase(app, prepare, write=False)
    storage = ExamStorage(app.state.settings.material_storage_dir)
    with storage.stage(
        user_id,
        space_id,
        attachment_id,
        manifest,
        min(app.state.settings.material_max_bytes, app.state.settings.exam_max_bytes),
    ) as staged:
        await staged.receive(chunks)
        if staged.sha256 != manifest.sha256 or staged.size_bytes != manifest.size_bytes:
            raise ProviderError("file_digest_mismatch", "实际文件与上传清单不一致", 422)

        def publish(sessions):
            with sessions.begin() as db:
                user = session_user(db, session_hash, lock=True)
                row = queries.own(db, user.id, space_id, diagnostic_id, lock=True)
                _, a = queries.attachment(db, user.id, space_id, diagnostic_id, attachment_id)
                if row.status != "draft" or row.generation != generation:
                    raise ProviderError("exam_not_draft", "试卷状态已变化，请刷新", 409)
                if not a.received:
                    staged.publish()
                    a.received = True
                    db.flush()
                result = queries.detail(db, user.id, space_id, row.id)
            return result

        result = await db_phase(app, publish)
        staged.keep()
        return result


def discard(db, user, space, diagnostic_id, storage_root):
    row = queries.own(db, user.id, space.id, diagnostic_id, lock=True)
    if row.status != "draft":
        raise ProviderError("exam_not_draft", "只能丢弃未开始的草稿", 409)
    storage = ExamStorage(storage_root)
    for a in db.scalars(select(ExamAttachment).where(ExamAttachment.diagnostic_id == row.id)):
        storage.delete(user.id, space.id, a.id)
    db.execute(delete(ExamAttachment).where(ExamAttachment.diagnostic_id == row.id))
    db.delete(row)
