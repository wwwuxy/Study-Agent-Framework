from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select

from app.api.deps import current_user, get_db, own_provider
from app.core.orchestrator import call_model
from app.core.security import validate_base_url
from app.db.models import AgentRun, MaterialAsset, ProviderConfig, StudySpace
from app.providers.base import ProviderError
from app.schemas.api import ProviderCreate, ProviderUpdate

router = APIRouter(prefix="/providers", tags=["providers"])


def public_provider(config):
    return {
        "id": config.id,
        "name": config.name,
        "provider_type": config.provider_type,
        "base_url": config.base_url,
        "chat_model": config.chat_model,
        "embedding_model": config.embedding_model,
        "has_api_key": bool(config.encrypted_api_key),
        "timeout_seconds": config.timeout_seconds,
        "tested": config.tested,
        "capabilities": config.capabilities,
    }


@router.get("")
async def list_providers(db=Depends(get_db), user=Depends(current_user)):
    return [
        public_provider(c)
        for c in db.scalars(
            select(ProviderConfig)
            .where(ProviderConfig.user_id == user.id)
            .order_by(ProviderConfig.created_at)
        ).all()
    ]


@router.post("", status_code=201)
async def create_provider(
    body: ProviderCreate, request: Request, db=Depends(get_db), user=Depends(current_user)
):
    if body.provider_type in {"fake", "fake_files"}:
        if not request.app.state.settings.enable_fake_provider:
            raise ProviderError("demo_disabled", "管理员未启用离线演示", 422)
    else:
        await validate_base_url(body.base_url, request.app.state.settings.allow_private_provider_urls)
    config = ProviderConfig(
        user_id=user.id,
        name=body.name,
        provider_type=body.provider_type,
        base_url=body.base_url,
        chat_model=body.chat_model,
        embedding_model=body.embedding_model,
        timeout_seconds=body.timeout_seconds,
        encrypted_api_key=request.app.state.vault.encrypt(body.api_key.get_secret_value()),
    )
    db.add(config)
    db.flush()
    return public_provider(config)


@router.patch("/{provider_id}")
async def update_provider(
    provider_id: str, body: ProviderUpdate, request: Request, db=Depends(get_db), user=Depends(current_user)
):
    config = own_provider(db, user.id, provider_id)
    if body.base_url and config.provider_type not in {"fake", "fake_files"}:
        await validate_base_url(body.base_url, request.app.state.settings.allow_private_provider_urls)
    changed = False
    for field in ("name", "base_url", "chat_model", "timeout_seconds", "embedding_model"):
        if getattr(body, field) is not None:
            setattr(config, field, getattr(body, field))
            changed |= field != "name"
    if "embedding_model" in body.model_fields_set:
        config.embedding_model = body.embedding_model
        changed = True
    if body.api_key:
        config.encrypted_api_key = request.app.state.vault.encrypt(body.api_key.get_secret_value())
        changed = True
    if changed:
        config.tested, config.capabilities = False, {}
    return public_provider(config)


@router.delete("/{provider_id}", status_code=204)
async def remove_provider(provider_id: str, db=Depends(get_db), user=Depends(current_user)):
    config = own_provider(db, user.id, provider_id)
    if db.scalar(select(StudySpace.id).where(StudySpace.provider_id == config.id)):
        raise ProviderError("provider_in_use", "请先将关联学习空间切换到其他已检测的模型，再删除凭证", 409)
    if db.scalar(
        select(MaterialAsset.id).where(
            MaterialAsset.provider_id == config.id, MaterialAsset.status != "deleted"
        )
    ):
        raise ProviderError("provider_in_use", "请先删除并清理关联资料，再删除凭证", 409)
    for asset in db.scalars(select(MaterialAsset).where(MaterialAsset.user_id == user.id)).all():
        if any(handle.get("provider_id") == config.id for handle in asset.remote_files):
            raise ProviderError(
                "provider_in_use", "该凭证仍用于旧版本资料的远端文件清理，请先删除资料并完成清理", 409
            )
    db.delete(config)
    return Response(status_code=204)


@router.post("/{provider_id}/test")
async def test_provider(provider_id: str, request: Request, db=Depends(get_db), user=Depends(current_user)):
    config = own_provider(db, user.id, provider_id)
    fields = (
        "provider_type",
        "base_url",
        "chat_model",
        "encrypted_api_key",
        "timeout_seconds",
        "embedding_model",
    )
    snapshot = tuple(getattr(config, field) for field in fields)
    # Invalidate stale success first; failed retests must disable subsequent paid tasks.
    config.tested, config.capabilities = False, {}
    db.commit()
    caps, run_id = await call_model(request, db, config, None, "probe")
    latest = db.scalar(
        select(ProviderConfig)
        .where(ProviderConfig.id == provider_id, ProviderConfig.user_id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if latest is None or snapshot != tuple(getattr(latest, field) for field in fields):
        db.get(AgentRun, run_id).error_code = "provider_config_changed"
        db.commit()
        raise ProviderError("provider_config_changed", "模型配置在检测期间发生变化，请重新检测", 409)
    if not caps.get("chat") or not caps.get("structured_json"):
        raise ProviderError("required_capability_missing", "模型不具备必需的聊天和结构化输出能力", 422)
    latest.tested, latest.capabilities = True, caps
    return {**caps, "run_id": run_id}


@router.get("/{provider_id}/capabilities")
async def capabilities(provider_id: str, db=Depends(get_db), user=Depends(current_user)):
    config = own_provider(db, user.id, provider_id)
    return {"tested": config.tested, **config.capabilities}
