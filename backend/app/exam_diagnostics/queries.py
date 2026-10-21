import base64
import json
from datetime import datetime

from sqlalchemy import and_, or_, select

from app.api.deps import own_space
from app.db.models import StudySpace, User, as_utc
from app.exam_diagnostics.models import ExamAttachment, ExamDiagnostic, ExamJob, ExamQuestion
from app.providers.base import ProviderError
from app.schemas.exams import ExamAttachmentView, ExamDetail, ExamPage, ExamQuestionView


def lock_space(db, user_id, space_id, *, allow_deleted=False):
    """All exam writes lock User → Space → Diagnostic → Job, including cleanup."""
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    space = db.scalar(
        select(StudySpace)
        .where(StudySpace.id == space_id, StudySpace.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not user or not space or (not allow_deleted and space.status in {"deleted", "archived"}):
        raise ProviderError("not_found", "学习空间不存在", 404)
    return space


def lock_diagnostic(db, user_id, space_id, diagnostic_id, *, allow_deleted=False):
    lock_space(db, user_id, space_id, allow_deleted=allow_deleted)
    row = db.scalar(
        select(ExamDiagnostic)
        .where(
            ExamDiagnostic.id == diagnostic_id,
            ExamDiagnostic.user_id == user_id,
            ExamDiagnostic.space_id == space_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not row:
        raise ProviderError("not_found", "试卷诊断不存在", 404)
    return row


def own(db, user_id, space_id, diagnostic_id, *, lock=False):
    if lock:
        lock_space(db, user_id, space_id)
    else:
        own_space(db, user_id, space_id)
    query = select(ExamDiagnostic).where(
        ExamDiagnostic.id == diagnostic_id,
        ExamDiagnostic.user_id == user_id,
        ExamDiagnostic.space_id == space_id,
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(query)
    if not row or row.status == "deleted":
        raise ProviderError("not_found", "试卷诊断不存在", 404)
    if row.canonical_id:
        return own(db, user_id, space_id, row.canonical_id, lock=lock)
    return row


def attachment(db, user_id, space_id, diagnostic_id, attachment_id):
    row = own(db, user_id, space_id, diagnostic_id)
    value = db.scalar(
        select(ExamAttachment).where(
            ExamAttachment.id == attachment_id,
            ExamAttachment.diagnostic_id == row.id,
            ExamAttachment.user_id == user_id,
            ExamAttachment.space_id == space_id,
        )
    )
    if not value:
        raise ProviderError("not_found", "试卷附件不存在", 404)
    return row, value


def detail(db, user_id, space_id, diagnostic_id):
    row = own(db, user_id, space_id, diagnostic_id)
    attachments = db.scalars(
        select(ExamAttachment).where(ExamAttachment.diagnostic_id == row.id).order_by(ExamAttachment.position)
    ).all()
    questions = db.scalars(
        select(ExamQuestion)
        .where(ExamQuestion.diagnostic_id == row.id)
        .order_by(ExamQuestion.created_at, ExamQuestion.id)
    ).all()
    job = db.scalar(
        select(ExamJob)
        .where(ExamJob.diagnostic_id == row.id, ExamJob.kind == "recognize")
        .order_by(ExamJob.created_at.desc(), ExamJob.id.desc())
    )
    pending = db.scalar(
        select(ExamJob.id).where(
            ExamJob.diagnostic_id == row.id, ExamJob.kind == "cleanup", ExamJob.status == "failed"
        )
    )
    return ExamDetail(
        id=row.id,
        study_space_id=space_id,
        name=row.name,
        exam_date=row.exam_date,
        status=row.status,
        version=row.version,
        created_at=as_utc(row.created_at).isoformat(),
        imported_at=as_utc(row.imported_at).isoformat() if row.imported_at else None,
        attachments=[
            ExamAttachmentView(**{k: getattr(a, k) for k in ExamAttachmentView.model_fields})
            for a in attachments
        ],
        questions=[
            ExamQuestionView(**{k: getattr(q, k) for k in ExamQuestionView.model_fields})
            for q in sorted(questions, key=lambda q: q.current.get("leaf_order", 0))
        ],
        task={
            "id": job.id,
            "status": job.status,
            "stage": job.stage,
            "attempts": job.attempts,
            "error_code": job.error_code,
            "error_message": job.error_message,
        }
        if job
        else None,
        report=row.data.get("report", {}),
        effective_evidence_count=sum(q.event_id is not None for q in questions),
        before=row.data.get("before", {}),
        after=row.data.get("after", {}),
        is_demo=row.data.get("is_demo", False),
        cleanup_warning="远端文件清理尚未确认，可重试诊断清理或在服务商控制台处理。" if pending else None,
    )


def page(db, user_id, space_id, before=None, limit=20):
    own_space(db, user_id, space_id)
    query = select(ExamDiagnostic).where(
        ExamDiagnostic.user_id == user_id,
        ExamDiagnostic.space_id == space_id,
        ExamDiagnostic.status.not_in(["duplicate", "deleted"]),
    )
    if before:
        try:
            sid, ts, key = json.loads(base64.urlsafe_b64decode(before + "=" * (-len(before) % 4)))
            stamp = datetime.fromisoformat(ts)
            if sid != space_id:
                raise ValueError()
        except (ValueError, TypeError, UnicodeError):
            raise ProviderError("invalid_cursor", "诊断分页标识无效", 422) from None
        query = query.where(
            or_(
                ExamDiagnostic.created_at < stamp,
                and_(ExamDiagnostic.created_at == stamp, ExamDiagnostic.id < key),
            )
        )
    rows = db.scalars(
        query.order_by(ExamDiagnostic.created_at.desc(), ExamDiagnostic.id.desc()).limit(limit + 1)
    ).all()
    cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        cursor = (
            base64.urlsafe_b64encode(
                json.dumps([space_id, as_utc(last.created_at).isoformat(), last.id]).encode()
            )
            .decode()
            .rstrip("=")
        )
    return ExamPage(items=[detail(db, user_id, space_id, r.id) for r in rows[:limit]], next_cursor=cursor)
