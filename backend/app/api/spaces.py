from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.api.deps import current_user, get_db, own_provider, own_space
from app.core.orchestrator import (
    call_model,
    concept_data,
    digest,
    profile,
    rebuild_states,
    save_plan,
)
from app.db.models import (
    AgentRun,
    ConceptPrerequisite,
    KnowledgeConcept,
    LearningEvent,
    MaterialAsset,
    MaterialJob,
    StudySpace,
    as_utc,
    new_id,
    utcnow,
)
from app.knowledge.materials import public_job
from app.knowledge.storage import MaterialStorage
from app.providers.base import ProviderError
from app.schemas.api import SpaceCreate, SpaceUpdate
from app.schemas.domain import Curriculum

router = APIRouter(prefix="/study-spaces", tags=["study-spaces"])


def public_space(space):
    return {
        "id": space.id,
        "goal": space.goal,
        "provider_id": space.provider_id,
        "allow_general_knowledge": space.allow_general_knowledge,
        "daily_minutes": space.daily_minutes,
        "target_date": space.target_date,
        "expected_level": space.expected_level,
        "status": space.status,
        "source_status": "model_generated_unverified",
        "created_at": space.created_at.isoformat(),
    }


@router.get("")
async def list_spaces(include_archived: bool = False, db=Depends(get_db), user=Depends(current_user)):
    query = select(StudySpace).where(StudySpace.user_id == user.id, StudySpace.status != "deleted")
    if not include_archived:
        query = query.where(StudySpace.status != "archived")
    return [public_space(s) for s in db.scalars(query.order_by(StudySpace.created_at)).all()]


@router.get("/deletion-jobs")
async def deletion_jobs(db=Depends(get_db), user=Depends(current_user)):
    """Only cleanup metadata, never the deleted goal or original filename."""
    jobs = db.scalars(
        select(MaterialJob)
        .join(StudySpace, MaterialJob.space_id == StudySpace.id)
        .where(MaterialJob.user_id == user.id, StudySpace.status == "deleted")
        .order_by(MaterialJob.created_at)
    ).all()
    retried = {job.data.get("parent_job") for job in jobs}
    result = []
    for job in jobs:
        asset = db.get(MaterialAsset, job.asset_id)
        if (
            job.kind == "cleanup"
            and job.status in {"queued", "running", "failed"}
            and job.id not in retried
            and (asset.status != "deleted" or asset.remote_files)
        ):
            result.append(public_job(job))
        elif (
            job.kind == "index"
            and job.status == "cancelled"
            and job.lease_until
            and as_utc(job.lease_until) > utcnow()
        ):
            result.append({**public_job(job), "status": "running", "stage": "waiting_upload"})
    return result


@router.post("", status_code=201)
async def create_space(body: SpaceCreate, request: Request, db=Depends(get_db), user=Depends(current_user)):
    fingerprint = digest(body.model_dump(mode="json"))
    existing = db.scalar(
        select(StudySpace).where(StudySpace.user_id == user.id, StudySpace.init_key == body.idempotency_key)
    )
    if existing:
        if existing.status == "deleted":
            raise ProviderError("space_deleted", "学习空间已永久删除，请使用新的请求标识", 409)
        if existing.request_digest != fingerprint:
            raise ProviderError("idempotency_conflict", "同一初始化键对应了不同配置", 409)
        if existing.status == "archived":
            raise ProviderError("space_archived", "学习空间已移除，请使用新的请求标识", 409)
        return public_space(existing)
    config = own_provider(db, user.id, body.provider_id, require_tested=True)
    curriculum, run_id = await call_model(
        request,
        db,
        config,
        None,
        "curriculum",
        Curriculum,
        {
            "task": "生成候选课程，知识点须唯一、前置关系为 DAG，建议 5–15 个核心概念。",
            "goal": body.goal,
            "expected_level": body.expected_level,
            "daily_minutes": body.daily_minutes,
            "target_date": str(body.target_date) if body.target_date else None,
        },
    )
    space = StudySpace(
        id=new_id(),
        user_id=user.id,
        provider_id=body.provider_id,
        goal=body.goal,
        daily_minutes=body.daily_minutes,
        target_date=body.target_date.isoformat() if body.target_date else None,
        expected_level=body.expected_level,
        init_key=body.idempotency_key,
        request_digest=fingerprint,
    )
    db.add(space)
    db.flush()
    db.get(AgentRun, run_id).space_id = space.id
    for concept in curriculum.concepts:
        db.add(KnowledgeConcept(space_id=space.id, key=concept.key, data=concept.model_dump()))
    db.flush()
    for concept in curriculum.concepts:
        for prerequisite in set(concept.prerequisites):
            db.add(
                ConceptPrerequisite(space_id=space.id, concept_key=concept.key, prerequisite_key=prerequisite)
            )
    await rebuild_states(db, space)
    save_plan(db, space)
    return public_space(space)


@router.delete("/{space_id}")
async def remove_space(space_id: str, request: Request, db=Depends(get_db), user=Depends(current_user)):
    space = db.scalar(
        select(StudySpace)
        .where(StudySpace.id == space_id, StudySpace.user_id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not space:
        raise ProviderError("not_found", "学习空间不存在", 404)
    from app.services.space_deletion import erase_space_content

    return erase_space_content(db, space, MaterialStorage(request.app.state.settings.material_storage_dir))


@router.get("/{space_id}")
async def get_space(space_id: str, db=Depends(get_db), user=Depends(current_user)):
    return public_space(own_space(db, user.id, space_id))


@router.patch("/{space_id}")
async def switch_provider(space_id: str, body: SpaceUpdate, db=Depends(get_db), user=Depends(current_user)):
    space = own_space(db, user.id, space_id)
    if body.provider_id is not None:
        config = own_provider(db, user.id, body.provider_id, require_tested=True)
        space.provider_id = config.id
    if body.allow_general_knowledge is not None:
        space.allow_general_knowledge = body.allow_general_knowledge
    return public_space(space)


@router.get("/{space_id}/concepts")
async def concepts(space_id: str, db=Depends(get_db), user=Depends(current_user)):
    space = own_space(db, user.id, space_id)
    return concept_data(db, space.id)


@router.get("/{space_id}/profile")
async def get_profile(space_id: str, db=Depends(get_db), user=Depends(current_user)):
    return profile(db, own_space(db, user.id, space_id))


@router.post("/{space_id}/profile/rebuild")
async def rebuild_profile(space_id: str, db=Depends(get_db), user=Depends(current_user)):
    space = own_space(db, user.id, space_id)
    await rebuild_states(db, space)
    save_plan(db, space)
    return profile(db, space)


@router.get("/{space_id}/plan")
async def get_plan(space_id: str, db=Depends(get_db), user=Depends(current_user)):
    space = own_space(db, user.id, space_id)
    from app.planning.intent import plan_view

    return plan_view(db, space)


@router.get("/{space_id}/events")
async def events(space_id: str, db=Depends(get_db), user=Depends(current_user)):
    space = own_space(db, user.id, space_id)
    rows = db.scalars(
        select(LearningEvent)
        .where(LearningEvent.space_id == space.id)
        .order_by(LearningEvent.occurred_at, LearningEvent.id)
    ).all()
    return [
        {"event_id": e.id, "type": e.type, "occurred_at": e.occurred_at.isoformat(), "payload": e.data}
        for e in rows
    ]


@router.get("/{space_id}/runs")
async def runs(space_id: str, db=Depends(get_db), user=Depends(current_user)):
    space = own_space(db, user.id, space_id)
    rows = db.scalars(
        select(AgentRun)
        .where(AgentRun.user_id == user.id, AgentRun.space_id == space.id)
        .order_by(AgentRun.created_at.desc())
        .limit(100)
    ).all()
    return [
        {
            "run_id": r.id,
            "model": r.model,
            "step": r.step,
            "elapsed_ms": r.elapsed_ms,
            "usage": r.usage,
            "error_code": r.error_code,
        }
        for r in rows
    ]
