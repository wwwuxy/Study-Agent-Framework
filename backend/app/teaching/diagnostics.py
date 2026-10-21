from sqlalchemy import select

from app.api.deps import own_provider
from app.core.orchestrator import call_model, concept_data, save_items, validate_items
from app.db.models import AssessmentItem
from app.knowledge.materials import check_citations
from app.knowledge.retrieval import teaching_sources
from app.providers.base import ProviderError
from app.schemas.domain import QuestionBatch
from app.teaching.presentation import attempts_map, public_question


async def ensure_diagnostics(request, db, space):
    items = db.scalars(
        select(AssessmentItem)
        .where(AssessmentItem.space_id == space.id, AssessmentItem.purpose == "diagnostic")
        .order_by(AssessmentItem.id)
    ).all()
    if not items:
        config = own_provider(db, space.user_id, space.provider_id, require_tested=True)
        sources = await teaching_sources(request, db, space, space.goal)
        batch, _ = await call_model(
            request,
            db,
            config,
            space.id,
            "diagnostic",
            QuestionBatch,
            {
                "task": "生成 5–10 道初始诊断题，覆盖不同核心知识，优先单知识点选择题。",
                "goal": space.goal,
                "concepts": concept_data(db, space.id),
                "sources": sources,
                "source_rule": "有教材证据时每题必须引用 sources 中的 source_id；资料不足不得编造。",
            },
        )
        if not 5 <= len(batch.items) <= 10:
            raise ProviderError("invalid_diagnostic_count", "初始诊断必须包含 5–10 道题")
        for question in batch.items:
            check_citations(db, space.id, question.source_ids, sources, bool(sources))
        validate_items(db, space.id, batch.items)
        items = save_items(db, space.id, batch.items, "diagnostic")
        items.sort(key=lambda item: item.id)
    attempted = attempts_map(db, space.id)
    return {
        "items": [public_question(db, i, attempted) for i in items],
        "attempts": attempted,
        "notice": "无需猜测已掌握程度。独立作答用于建立初始学习证据；标准答案本身由模型生成、待核实。",
    }
