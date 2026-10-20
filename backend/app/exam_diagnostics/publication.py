from datetime import date

from sqlalchemy import select

from app.core.orchestrator import append_event, digest, profile, rebuild_states, save_plan
from app.db.models import ProviderConfig, StudySpace, User, as_utc, new_id
from app.exam_diagnostics import queries
from app.exam_diagnostics.evidence import assessment_time, event_payload, qualify
from app.exam_diagnostics.models import ExamDiagnostic, ExamJob, ExamQuestion
from app.exam_diagnostics.report import leaves, summarize
from app.knowledge.materials import fingerprint
from app.providers.base import ProviderError


def state_snapshot(db, space):
    return {s["concept_id"]: s for s in profile(db, space)["states"]}


def guard(db, space, claim, now):
    db.scalar(select(User).where(User.id == claim.user_id).with_for_update())
    space = db.scalar(
        select(StudySpace)
        .where(StudySpace.id == claim.space_id, StudySpace.user_id == claim.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not space or space.status in {"deleted", "archived"}:
        raise ProviderError("not_found", "学习空间不存在", 404)
    row = db.scalar(
        select(ExamDiagnostic)
        .where(ExamDiagnostic.id == claim.diagnostic_id, ExamDiagnostic.space_id == space.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    job = db.scalar(
        select(ExamJob)
        .where(ExamJob.id == claim.job_id, ExamJob.diagnostic_id == claim.diagnostic_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        not row
        or not job
        or row.generation != claim.generation
        or job.generation != claim.generation
        or job.lease_token != claim.token
        or job.status != "running"
        or not job.lease_until
        or as_utc(job.lease_until) <= now
    ):
        raise ProviderError("stale_exam_job", "试卷任务已取消、过期或被其他进程接管", 409)
    config = db.get(ProviderConfig, space.provider_id)
    if (
        not config
        or config.id != job.provider_id
        or not config.tested
        or fingerprint(config) != job.data.get("provider_fingerprint")
    ):
        raise ProviderError("exam_provider_changed", "模型配置已变化，请重新授权并重试", 409)
    return row, job


async def add_evidence(db, space, row, question, now):
    q = question.current
    from app.schemas.exams import RecognizedQuestion

    recognized = RecognizedQuestion.model_validate(q)
    valid, reason = qualify(recognized)
    if not valid:
        question.exclusion_reason = reason
        return
    if question.event_id:
        return
    original_date = date.fromisoformat(row.exam_date) if row.exam_date else None
    imported_at = as_utc(row.imported_at) if row.imported_at else now
    user = db.get(User, space.user_id)
    stamp, _ = assessment_time(original_date, user.timezone, imported_at)
    payload = event_payload(row.id, recognized, imported_at, original_date)
    event = append_event(
        db,
        space,
        "exam_question_imported",
        "exam_" + digest([row.id, question.leaf_key]),
        payload,
        occurred_at=stamp,
    )
    question.event_id = event.id
    question.exclusion_reason = None


async def publish(db, space, claim, recognition, advice, *, now):
    existing = db.get(ExamDiagnostic, claim.diagnostic_id)
    if existing and existing.status == "completed":
        return queries.detail(db, claim.user_id, claim.space_id, claim.diagnostic_id)
    row, job = guard(db, space, claim, now)
    before = state_snapshot(db, space)
    row.imported_at = now
    for q in leaves(recognition):
        question = ExamQuestion(
            id=new_id(),
            user_id=space.user_id,
            space_id=space.id,
            diagnostic_id=row.id,
            leaf_key=q.key,
            original=q.model_dump(),
            current=q.model_dump(),
        )
        db.add(question)
        db.flush()
        await add_evidence(db, space, row, question, now)
    await rebuild_states(db, space)
    plan = save_plan(db, space)
    row.status = "completed"
    row.version += 1
    row.data = {
        **row.data,
        "report": {
            **summarize(recognition),
            "advice": advice.model_dump(),
            "next_action": plan["next_action"],
        },
        "before": before,
        "after": state_snapshot(db, space),
    }
    job.status = "succeeded"
    job.stage = "completed"
    job.active_space_id = None
    job.lease_token = None
    job.lease_until = None
    db.flush()
    return queries.detail(db, space.user_id, space.id, row.id)
