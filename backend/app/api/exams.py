"""Authenticated external-paper endpoints. Upload streaming owns short transactions."""

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import FileResponse

from app.api.deps import current_user, get_db, own_provider, own_space
from app.core.security import token_hash
from app.exam_diagnostics import drafts, queries, queue, review
from app.exam_diagnostics.storage import ExamStorage
from app.providers.base import ProviderError
from app.schemas.exams import (
    ExamCapabilities,
    ExamCreate,
    ExamDetail,
    ExamPage,
    ExamQuestionPatch,
    ExamRetry,
    ExamStart,
)

router = APIRouter(prefix="/study-spaces/{space_id}/exam-diagnostics", tags=["exam diagnostics"])


@router.get("/capabilities", response_model=ExamCapabilities)
async def capabilities(space_id: str, request: Request, db=Depends(get_db), user=Depends(current_user)):
    space = own_space(db, user.id, space_id)
    config = own_provider(db, user.id, space.provider_id)
    caps = config.capabilities if config.tested else {}
    settings = request.app.state.settings
    return ExamCapabilities(
        provider_name=config.name,
        pdf=bool(caps.get("file_input") and "application/pdf" in caps.get("supported_mime_types", [])),
        images=caps.get("supported_image_mime_types", []) if caps.get("image_input") else [],
        max_bytes=min(settings.material_max_bytes, settings.exam_max_bytes),
        max_total_bytes=2 * min(settings.material_max_bytes, settings.exam_max_bytes),
        max_images=settings.exam_max_images,
        max_questions=settings.exam_max_questions,
        is_demo=bool(caps.get("is_demo")),
    )


@router.post("", response_model=ExamDetail, status_code=201)
async def create(
    space_id: str, body: ExamCreate, request: Request, db=Depends(get_db), user=Depends(current_user)
):
    return drafts.create_draft(db, user, own_space(db, user.id, space_id), body, request.app.state.settings)


@router.put(
    "/{diagnostic_id}/attachments/{attachment_id}",
    response_model=ExamDetail,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                mime: {"schema": {"type": "string", "format": "binary"}}
                for mime in ("application/pdf", "image/png", "image/jpeg")
            },
        }
    },
)
async def upload(space_id: str, diagnostic_id: str, attachment_id: str, request: Request):
    return await drafts.receive_attachment(
        request.app,
        token_hash(request.cookies.get("study_session", "")),
        space_id,
        diagnostic_id,
        attachment_id,
        request.stream(),
        request.headers.get("content-type", "").split(";")[0],
    )


@router.get("", response_model=ExamPage)
async def listing(
    space_id: str,
    before: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(current_user),
):
    return queries.page(db, user.id, space_id, before, limit)


@router.get("/{diagnostic_id}", response_model=ExamDetail)
async def detail(space_id: str, diagnostic_id: str, db=Depends(get_db), user=Depends(current_user)):
    return queries.detail(db, user.id, space_id, diagnostic_id)


@router.get("/{diagnostic_id}/attachments/{attachment_id}/download")
async def download(
    space_id: str,
    diagnostic_id: str,
    attachment_id: str,
    request: Request,
    db=Depends(get_db),
    user=Depends(current_user),
):
    _, a = queries.attachment(db, user.id, space_id, diagnostic_id, attachment_id)
    path = ExamStorage(request.app.state.settings.material_storage_dir).path(user.id, space_id, a.id)
    if not a.received or not path.exists():
        raise ProviderError("file_unavailable", "原始试卷不可用", 404)
    return FileResponse(
        path, media_type=a.mime_type, filename=a.filename, content_disposition_type="attachment"
    )


@router.delete("/{diagnostic_id}/draft", status_code=204)
async def discard(
    space_id: str, diagnostic_id: str, request: Request, db=Depends(get_db), user=Depends(current_user)
):
    drafts.discard(
        db,
        user,
        own_space(db, user.id, space_id),
        diagnostic_id,
        request.app.state.settings.material_storage_dir,
    )
    return Response(status_code=204)


@router.post("/{diagnostic_id}/start", response_model=ExamDetail, status_code=202)
async def start(
    space_id: str,
    diagnostic_id: str,
    body: ExamStart,
    request: Request,
    db=Depends(get_db),
    user=Depends(current_user),
):
    return queue.start(
        db, user, own_space(db, user.id, space_id), diagnostic_id, body, request.app.state.settings
    )


@router.post("/{diagnostic_id}/retry", response_model=ExamDetail, status_code=202)
async def retry(
    space_id: str, diagnostic_id: str, body: ExamRetry, db=Depends(get_db), user=Depends(current_user)
):
    return queue.retry(db, user, own_space(db, user.id, space_id), diagnostic_id, body)


@router.post("/{diagnostic_id}/cancel", response_model=ExamDetail)
async def cancel(space_id: str, diagnostic_id: str, db=Depends(get_db), user=Depends(current_user)):
    return queue.cancel(db, user, own_space(db, user.id, space_id), diagnostic_id)


@router.patch("/{diagnostic_id}/questions/{question_id}", response_model=ExamDetail)
async def patch(
    space_id: str,
    diagnostic_id: str,
    question_id: str,
    body: ExamQuestionPatch,
    db=Depends(get_db),
    user=Depends(current_user),
):
    return await review.patch(db, user, own_space(db, user.id, space_id), diagnostic_id, question_id, body)
