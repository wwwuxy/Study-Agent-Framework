from pydantic import ValidationError
from sqlalchemy import select

from app.core.orchestrator import digest, rebuild_states, save_plan
from app.db.models import KnowledgeConcept, utcnow
from app.exam_diagnostics import queries
from app.exam_diagnostics.models import ExamQuestion
from app.exam_diagnostics.publication import add_evidence, state_snapshot
from app.exam_diagnostics.report import summarize
from app.providers.base import ProviderError
from app.schemas.exams import ExamRecognition, RecognizedQuestion


async def patch(db, user, space, diagnostic_id, question_id, body):
    row = queries.own(db, user.id, space.id, diagnostic_id, lock=True)
    q = db.scalar(
        select(ExamQuestion)
        .where(ExamQuestion.id == question_id, ExamQuestion.diagnostic_id == row.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not q:
        raise ProviderError("not_found", "试卷题目不存在", 404)
    hashed = digest(body.model_dump(mode="json"))
    previous = q.revisions.get(body.idempotency_key)
    if previous:
        if previous["digest"] != hashed:
            raise ProviderError("idempotency_conflict", "核对键已用于其他内容", 409)
        return queries.detail(db, user.id, space.id, row.id)
    if row.status != "completed" or q.event_id:
        raise ProviderError("exam_question_readonly", "已入库题目只读，不能重复累积证据", 409)
    if q.version != body.expected_version:
        raise ProviderError("exam_version_conflict", "题目已更新，请刷新后核对", 409)
    if len(q.revisions) >= 100:
        raise ProviderError("exam_revision_limit", "该题核对次数超过限制", 429)
    updated = dict(q.current)
    fields = body.model_fields_set - {"idempotency_key", "expected_version"}
    for field in fields:
        updated[field] = getattr(body, field)
    if updated.get("result") is None:
        raise ProviderError("invalid_exam_patch", "请选择核对结果", 422)
    if body.concept_ids is not None:
        actual = set(db.scalars(select(KnowledgeConcept.key).where(KnowledgeConcept.space_id == space.id)))
        if not set(body.concept_ids) <= actual:
            raise ProviderError("invalid_exam_mapping", "知识点不属于当前空间", 422)
        updated["mapping_confidence"] = "high" if len(body.concept_ids) == 1 else "low"
    # Manual correctness cannot upgrade the original visual teacher-mark evidence.
    original = RecognizedQuestion.model_validate(q.original)
    try:
        current = RecognizedQuestion.model_validate(updated)
    except ValidationError:
        raise ProviderError("invalid_exam_patch", "核对分值或知识点格式无效", 422) from None
    if (
        not original.teacher_mark_clear
        or original.recognition_confidence != "high"
        or current.result != original.teacher_result
    ):
        current.teacher_mark_clear = False
    if current.score is not None and current.max_score is not None:
        numeric = (
            "correct"
            if current.score == current.max_score
            else "incorrect"
            if current.score == 0
            else "partial"
        )
        if numeric != current.result:
            current.teacher_mark_clear = False
    q.current = current.model_dump()
    q.version += 1
    q.revisions = {
        **q.revisions,
        body.idempotency_key: {
            "digest": hashed,
            "changes": body.model_dump(mode="json", exclude={"idempotency_key", "expected_version"}),
            "source": "user_review",
            "at": utcnow().isoformat(),
        },
    }
    before = state_snapshot(db, space)
    await add_evidence(db, space, row, q, utcnow())
    await rebuild_states(db, space)
    plan = save_plan(db, space)
    items = db.scalars(select(ExamQuestion).where(ExamQuestion.diagnostic_id == row.id)).all()
    old_report = row.data["report"]
    rec = ExamRecognition(
        coverage_complete=old_report["coverage_complete"],
        coverage_note=old_report["coverage_note"],
        stated_score=old_report["stated_score"],
        stated_max_score=old_report["stated_max_score"],
        questions=[RecognizedQuestion.model_validate(item.current) for item in items],
    )
    row.data = {
        **row.data,
        "report": {**old_report, **summarize(rec), "next_action": plan["next_action"], "advice_stale": True},
        "before": row.data.get("before", before),
        "after": state_snapshot(db, space),
    }
    row.version += 1
    db.flush()
    return queries.detail(db, user.id, space.id, row.id)
