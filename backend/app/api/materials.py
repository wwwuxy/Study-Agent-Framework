import hashlib
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import delete, select

from app.api.deps import current_user, get_db, own_provider, own_space
from app.core.orchestrator import digest
from app.db.models import MaterialAsset, MaterialJob, MaterialSection, new_id
from app.jobs.materials import detach_sources, run_job
from app.knowledge.materials import fingerprint, new_job, own_asset, public_job, source_row
from app.knowledge.retrieval import retrieve
from app.knowledge.storage import MaterialStorage, validate_pdf
from app.providers.base import CapabilityNotSupported, ProviderError
from app.schemas.api import IdempotentRequest
from app.schemas.materials import MaterialRetry, MaterialSearch

router = APIRouter(tags=["materials"])


def public_asset(db, asset, detail=False):
    job = db.scalar(
        select(MaterialJob)
        .where(MaterialJob.asset_id == asset.id)
        .order_by(MaterialJob.created_at.desc())
        .limit(1)
    )
    if asset.status == "deleting" or asset.warning:
        pending_cleanup = db.scalar(
            select(MaterialJob)
            .where(
                MaterialJob.asset_id == asset.id,
                MaterialJob.kind == "cleanup",
                MaterialJob.status.in_(["queued", "running", "failed"]),
            )
            .order_by(MaterialJob.created_at.desc())
            .limit(1)
        )
        job = pending_cleanup or job
    result = {
        key: getattr(asset, key)
        for key in (
            "id",
            "space_id",
            "filename",
            "mime_type",
            "size_bytes",
            "status",
            "use_embeddings",
            "warning",
        )
    }
    result.update(
        job_id=job.id if job else None,
        job=public_job(job) if job else None,
        retention_notice="原文保存在本机；远端处理与保留遵循所选服务商政策，删除将尝试清理远端文件。",
    )
    if detail:
        result["sections"] = (
            [
                {**source_row(section, asset), **section.data}
                for section in db.scalars(
                    select(MaterialSection).where(MaterialSection.asset_id == asset.id)
                ).all()
            ]
            if asset.status == "ready"
            else []
        )
    return result


def require_files(config, embeddings):
    if not config.capabilities.get("file_input") or "application/pdf" not in config.capabilities.get(
        "supported_mime_types", []
    ):
        raise CapabilityNotSupported()
    if embeddings and not config.capabilities.get("embedding"):
        raise CapabilityNotSupported()


@router.post(
    "/study-spaces/{space_id}/materials",
    status_code=202,
    summary="上传授权的 PDF 并创建持久任务",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
        },
        "parameters": [
            {
                "name": name,
                "in": "header",
                "required": required,
                "description": description,
                "schema": {"type": "string"},
            }
            for name, required, description in [
                ("X-Filename", True, "URL 编码的原始 PDF 文件名"),
                ("Idempotency-Key", True, "1–100 字母数字、下划线、短横线"),
                ("X-File-Consent", True, "必须为 true：本次同意远端理解和保留政策"),
                ("X-Use-Embeddings", False, "true 表示同意本次额外调用远端 Embedding"),
            ]
        ],
    },
)
async def upload(space_id: str, request: Request, db=Depends(get_db), user=Depends(current_user)):
    space = own_space(db, user.id, space_id)
    config = own_provider(db, user.id, space.provider_id, True)
    embeddings = request.headers.get("x-use-embeddings", "false") == "true"
    require_files(config, embeddings)
    if request.headers.get("x-file-consent") != "true":
        raise ProviderError(
            "file_consent_required", "本次上传须明确同意将资料交给所选远端模型处理，并知悉服务商保留政策", 422
        )
    try:
        key = IdempotentRequest(idempotency_key=request.headers.get("idempotency-key", "")).idempotency_key
    except ValidationError:
        raise ProviderError("invalid_idempotency_key", "上传必须携带有效的 Idempotency-Key", 422) from None

    limit = request.app.state.settings.material_max_bytes
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise ProviderError("file_too_large", "资料超过实例大小上限", 413)
        chunks.append(chunk)
    data = b"".join(chunks)
    filename = unquote(request.headers.get("x-filename", ""))
    mime = request.headers.get("content-type", "").split(";")[0]
    validate_pdf(filename, mime, data, limit)
    sha = hashlib.sha256(data).hexdigest()
    request_hash = digest([filename, mime, sha, embeddings])
    existing = db.scalar(
        select(MaterialAsset).where(MaterialAsset.space_id == space.id, MaterialAsset.upload_key == key)
    )
    if existing:
        if existing.request_digest != request_hash:
            raise ProviderError("idempotency_conflict", "同一上传键不能用于不同文件或配置", 409)
        if existing.status in {"deleted", "deleting"}:
            raise ProviderError("material_deleted", "资料已删除，请使用新的上传键", 409)
        return public_asset(db, existing)
    asset = MaterialAsset(
        id=new_id(),
        user_id=user.id,
        space_id=space.id,
        provider_id=config.id,
        provider_fingerprint=fingerprint(config),
        upload_key=key,
        request_digest=request_hash,
        filename=filename,
        mime_type=mime,
        size_bytes=len(data),
        sha256=sha,
        use_embeddings=embeddings,
    )
    db.add(asset)
    db.flush()
    storage = MaterialStorage(request.app.state.settings.material_storage_dir)
    storage.save(user.id, space.id, asset.id, data)
    try:
        new_job(db, asset, "upload_" + key)
        db.commit()
    except BaseException:
        storage.delete(user.id, space.id, asset.id)
        raise
    return public_asset(db, asset)


@router.get("/study-spaces/{space_id}/materials")
async def list_materials(space_id: str, db=Depends(get_db), user=Depends(current_user)):
    space = own_space(db, user.id, space_id)
    # Tombstones remain visible here so pending remote cleanup is never hidden.
    return [
        public_asset(db, asset)
        for asset in db.scalars(
            select(MaterialAsset)
            .where(MaterialAsset.space_id == space.id, MaterialAsset.status != "deleted")
            .order_by(MaterialAsset.created_at)
        ).all()
    ]


@router.post("/study-spaces/{space_id}/materials/search")
async def search(
    space_id: str, body: MaterialSearch, request: Request, db=Depends(get_db), user=Depends(current_user)
):
    space = own_space(db, user.id, space_id)
    return await retrieve(request, db, space, body.query, body.mode, body.limit)


@router.get("/study-spaces/{space_id}/materials/{asset_id}")
async def get_material(space_id: str, asset_id: str, db=Depends(get_db), user=Depends(current_user)):
    return public_asset(db, own_asset(db, user.id, space_id, asset_id), True)


@router.get("/study-spaces/{space_id}/materials/{asset_id}/download")
async def download(
    space_id: str, asset_id: str, request: Request, db=Depends(get_db), user=Depends(current_user)
):
    asset = own_asset(db, user.id, space_id, asset_id)
    path = MaterialStorage(request.app.state.settings.material_storage_dir).path(user.id, space_id, asset.id)
    if not path.exists():
        raise ProviderError("file_unavailable", "原始文件已不可用", 404)
    return FileResponse(
        path, media_type=asset.mime_type, filename=asset.filename, content_disposition_type="attachment"
    )


@router.post("/study-spaces/{space_id}/materials/{asset_id}/reindex", status_code=202)
async def reindex(
    space_id: str,
    asset_id: str,
    body: MaterialRetry,
    request: Request,
    db=Depends(get_db),
    user=Depends(current_user),
):
    space = own_space(db, user.id, space_id)
    asset = own_asset(db, user.id, space.id, asset_id)
    key = "reindex_" + body.idempotency_key
    existing = db.scalar(
        select(MaterialJob).where(MaterialJob.space_id == space.id, MaterialJob.request_key == key)
    )
    if existing:
        if existing.asset_id != asset.id or existing.data.get("request_digest") != digest(body.model_dump()):
            raise ProviderError("idempotency_conflict", "重索引键已用于其他请求", 409)
        return {"job_id": existing.id, "job": public_job(existing)}
    if not body.consent:
        raise ProviderError("file_consent_required", "重索引需要再次授权远端处理", 422)
    config = own_provider(db, user.id, space.provider_id, True)
    require_files(config, body.use_embeddings)
    asset.generation += 1
    asset.status, asset.use_embeddings = "queued", body.use_embeddings
    asset.provider_id, asset.provider_fingerprint = config.id, fingerprint(config)
    for job in db.scalars(
        select(MaterialJob).where(
            MaterialJob.asset_id == asset.id,
            MaterialJob.kind == "index",
            MaterialJob.status.in_(["queued", "running"]),
        )
    ).all():
        job.status = "cancelled"
    job = new_job(db, asset, key, data={"request_digest": digest(body.model_dump())})
    return {"job_id": job.id, "job": public_job(job)}


@router.delete("/study-spaces/{space_id}/materials/{asset_id}")
async def delete_material(
    space_id: str, asset_id: str, request: Request, db=Depends(get_db), user=Depends(current_user)
):
    asset = own_asset(db, user.id, space_id, asset_id, True)
    if asset.status in {"deleting", "deleted"}:
        return public_asset(db, asset)
    asset.generation += 1
    asset.status = "deleting"
    for job in db.scalars(select(MaterialJob).where(MaterialJob.asset_id == asset.id)).all():
        if job.status in {"queued", "running", "failed"}:
            job.status = "cancelled"
        job.data = {}
    ids = db.scalars(select(MaterialSection.id).where(MaterialSection.asset_id == asset.id)).all()
    detach_sources(db, space_id, ids)
    db.execute(delete(MaterialSection).where(MaterialSection.asset_id == asset.id))
    MaterialStorage(request.app.state.settings.material_storage_dir).delete(user.id, space_id, asset.id)
    new_job(db, asset, "delete_" + new_id(), "cleanup")
    db.flush()
    return public_asset(db, asset)


def own_job(db, user_id, job_id):
    job = db.scalar(select(MaterialJob).where(MaterialJob.id == job_id, MaterialJob.user_id == user_id))
    if not job:
        raise ProviderError("not_found", "任务不存在", 404)
    return job


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, db=Depends(get_db), user=Depends(current_user)):
    return public_job(own_job(db, user.id, job_id))


@router.post("/jobs/{job_id}/run")
async def process_job(job_id: str, request: Request, db=Depends(get_db), user=Depends(current_user)):
    own_job(db, user.id, job_id)
    db.commit()
    await run_job(request.app, job_id)
    db.expire_all()
    return public_job(own_job(db, user.id, job_id))


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, db=Depends(get_db), user=Depends(current_user)):
    job = own_job(db, user.id, job_id)
    if job.kind == "cleanup":
        raise ProviderError("cleanup_required", "删除清理任务不可取消，可重试或到服务商控制台清理", 409)
    if job.status in {"queued", "running"}:
        job.status = "cancelled"
        asset = db.get(MaterialAsset, job.asset_id)
        asset.generation += 1
        asset.status = "cancelled"
    return public_job(job)


@router.post("/jobs/{job_id}/retry", status_code=202)
async def retry_job(job_id: str, body: IdempotentRequest, db=Depends(get_db), user=Depends(current_user)):
    job = own_job(db, user.id, job_id)
    asset = db.get(MaterialAsset, job.asset_id)
    key = "retry_" + body.idempotency_key
    existing = db.scalar(
        select(MaterialJob).where(MaterialJob.space_id == job.space_id, MaterialJob.request_key == key)
    )
    if existing:
        if existing.data.get("parent_job") != job.id:
            raise ProviderError("idempotency_conflict", "重试键已被使用", 409)
        return public_job(existing)
    if job.status != "failed" or (job.kind == "index" and asset.generation != job.generation):
        raise ProviderError("job_not_retryable", "仅当前版本的失败任务可重试；已取消的资料请重新索引", 409)
    if job.kind == "index":
        asset.status = "queued"
    retry = new_job(db, asset, key, job.kind, {**job.data, "parent_job": job.id})
    return public_job(retry)
