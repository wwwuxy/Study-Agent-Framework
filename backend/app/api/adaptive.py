from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import current_user, get_db, own_space
from app.core.orchestrator import concept_data
from app.db.models import AssessmentItem, utcnow
from app.learner.parameters import algorithm_manifest
from app.learner.report import build_report
from app.providers.base import ProviderError

router = APIRouter(prefix="/study-spaces/{space_id}", tags=["adaptive-learning"])


@router.get("/algorithms")
async def algorithms(space_id: str, db=Depends(get_db), user=Depends(current_user)):
    own_space(db, user.id, space_id)
    return algorithm_manifest(db.info.get("algorithm_parameters"))


@router.get("/q-matrix")
async def qmatrix(space_id: str, db=Depends(get_db), user=Depends(current_user)):
    space = own_space(db, user.id, space_id)
    return {
        "version": "qmatrix_v1",
        "concepts": [{"key": c["key"], "name": c["name"]} for c in concept_data(db, space.id)],
        "items": [
            {
                "item_id": q.id,
                "concept_ids": q.data["concept_keys"],
                "purpose": q.purpose,
                "assessment_mode": "single" if len(q.data["concept_keys"]) == 1 else "composite",
            }
            for q in db.scalars(select(AssessmentItem).where(AssessmentItem.space_id == space.id))
        ],
    }


@router.get("/report")
async def report(
    space_id: str, days: int = Query(7, enum=[7, 30]), db=Depends(get_db), user=Depends(current_user)
):
    if days not in {7, 30}:
        raise ProviderError("invalid_report_window", "报告窗口只支持 7 或 30 天", 422)
    return await build_report(db, own_space(db, user.id, space_id), days, utcnow())
