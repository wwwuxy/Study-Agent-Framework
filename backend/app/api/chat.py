from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app.chat.service import db_phase, send_turn
from app.chat.turns import read_history
from app.core.security import token_hash
from app.schemas.chat import ChatSend, ChatTurnPage, ChatTurnResponse, PlanRevisionPage

router = APIRouter(prefix="/study-spaces/{space_id}", tags=["planning-chat"])


def session_hash(request):
    return token_hash(request.cookies.get("study_session", ""))


@router.post("/chat/turns", response_model=ChatTurnResponse, status_code=201)
async def send(space_id: str, body: ChatSend, request: Request):
    result = await send_turn(request.app, session_hash(request), space_id, body)
    return JSONResponse(result.response.model_dump(mode="json"), status_code=result.http_status)


@router.get("/chat/turns", response_model=ChatTurnPage)
async def history(
    space_id: str, request: Request, before: str | None = None, limit: int = Query(30, ge=1, le=100)
):
    return await db_phase(
        request.app, read_history, session_hash(request), space_id, before=before, limit=limit, write=False
    )


@router.get("/chat/turns/{turn_id}", response_model=ChatTurnResponse)
async def turn(space_id: str, turn_id: str, request: Request):
    return await db_phase(
        request.app, read_history, session_hash(request), space_id, turn_id=turn_id, write=False
    )


@router.get("/plan/revisions", response_model=PlanRevisionPage)
async def revisions(
    space_id: str, request: Request, before: str | None = None, limit: int = Query(30, ge=1, le=100)
):
    return await db_phase(
        request.app,
        read_history,
        session_hash(request),
        space_id,
        before=before,
        limit=limit,
        revisions=True,
        write=False,
    )
