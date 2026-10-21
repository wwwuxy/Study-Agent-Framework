from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.activity.analysis import public_analysis, send_analysis
from app.activity.presentation import owned_page
from app.activity.quota import usage_view
from app.api.deps import current_user, get_db, own_space
from app.core.security import token_hash
from app.db.models import AnalysisRun, utcnow
from app.providers.base import ProviderError
from app.schemas.activity import Page
from app.schemas.analyses import AnalysisRequest, AnalysisResponse, AnalysisUsageResponse

router = APIRouter(tags=["activity-analysis"])


@router.post("/study-spaces/{space_id}/analyses", response_model=AnalysisResponse, status_code=201)
async def analyze(space_id: str, request: Request, body: AnalysisRequest):
    result = await send_analysis(
        request.app, token_hash(request.cookies.get("study_session", "")), space_id, body
    )
    return JSONResponse(
        result.model_dump(mode="json"), status_code=202 if result.status == "processing" else 201
    )


@router.get("/study-spaces/{space_id}/analyses", response_model=Page[AnalysisResponse])
async def list_analyses(
    space_id: str,
    cursor: str | None = Query(None, max_length=1000),
    limit: int = Query(30, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(current_user),
):
    own_space(db, user.id, space_id)
    return owned_page(db, AnalysisRun, user.id, public_analysis, cursor, limit, space_id=space_id)


@router.get("/study-spaces/{space_id}/analyses/{analysis_id}", response_model=AnalysisResponse)
async def analysis(space_id: str, analysis_id: str, db=Depends(get_db), user=Depends(current_user)):
    own_space(db, user.id, space_id)
    row = db.scalar(
        select(AnalysisRun).where(
            AnalysisRun.id == analysis_id, AnalysisRun.space_id == space_id, AnalysisRun.user_id == user.id
        )
    )
    if not row:
        raise ProviderError("not_found", "分析不存在", 404)
    return public_analysis(row)


@router.get("/analysis-usage", response_model=AnalysisUsageResponse)
async def usage(request: Request, db=Depends(get_db), user=Depends(current_user)):
    return usage_view(db, user.id, utcnow(), request.app.state.settings)


@router.get("/analyses", response_model=Page[AnalysisResponse])
async def account_analyses(
    cursor: str | None = Query(None, max_length=1000),
    limit: int = Query(30, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(current_user),
):
    return owned_page(db, AnalysisRun, user.id, public_analysis, cursor, limit)
