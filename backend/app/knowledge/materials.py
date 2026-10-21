"""Scoped material metadata, source resolution and credential identity."""

import hashlib
import json

from sqlalchemy import select

from app.db.models import MaterialAsset, MaterialJob, MaterialSection, StudySpace, new_id, utcnow
from app.providers.base import ProviderError


def fingerprint(config):
    return hashlib.sha256(
        json.dumps(
            [
                config.id,
                config.provider_type,
                config.base_url,
                config.chat_model,
                config.embedding_model,
                config.encrypted_api_key,
            ]
        ).encode()
    ).hexdigest()


def own_asset(db, user_id, space_id, asset_id, include_deleted=False):
    asset = db.scalar(
        select(MaterialAsset)
        .join(StudySpace, MaterialAsset.space_id == StudySpace.id)
        .where(
            MaterialAsset.id == asset_id,
            MaterialAsset.user_id == user_id,
            MaterialAsset.space_id == space_id,
            StudySpace.status.not_in(["archived", "deleted"]),
        )
    )
    if not asset or (not include_deleted and asset.status in {"deleted", "deleting"}):
        raise ProviderError("not_found", "资料不存在", 404)
    return asset


def public_job(job):
    return {
        key: getattr(job, key)
        for key in (
            "id",
            "asset_id",
            "space_id",
            "kind",
            "status",
            "stage",
            "progress",
            "attempts",
            "error_code",
            "error_message",
        )
    }


def inflight_indexes():
    # Cancelled workers may still be awaiting an upload response. Their lease
    # bounds that wait; keep origin credentials until they return or time out.
    return select(MaterialJob).where(
        MaterialJob.kind == "index",
        MaterialJob.status.in_(["running", "cancelled"]),
        MaterialJob.lease_until > utcnow(),
    )


def new_job(db, asset, key, kind="index", data=None):
    job = MaterialJob(
        id=new_id(),
        user_id=asset.user_id,
        space_id=asset.space_id,
        asset_id=asset.id,
        kind=kind,
        request_key=key,
        generation=asset.generation,
        data=data or {},
    )
    db.add(job)
    db.flush()
    return job


def source_row(section, asset):
    return {
        "source_id": section.id,
        "study_space_id": asset.space_id,
        "document_id": asset.id,
        "filename": asset.filename,
        "heading": section.data["heading"],
        "summary": section.data["summary"],
        "locator": section.data.get("locator", {}),
        "locator_verified": False,
        "source_status": "user_material_derived",
        "is_demo": section.data.get("is_demo", False),
    }


def resolve_sources(db, space_id, ids):
    if not ids:
        return []
    rows = db.execute(
        select(MaterialSection, MaterialAsset)
        .join(MaterialAsset, MaterialSection.asset_id == MaterialAsset.id)
        .where(
            MaterialSection.space_id == space_id,
            MaterialAsset.space_id == space_id,
            MaterialAsset.status == "ready",
            MaterialSection.id.in_(ids),
        )
    ).all()
    indexed = {section.id: source_row(section, asset) for section, asset in rows}
    return [indexed[i] for i in dict.fromkeys(ids) if i in indexed]


def check_citations(db, space_id, ids, sources, required=False):
    allowed = {s["source_id"] for s in sources}
    if (required and not ids) or not set(ids) <= allowed:
        raise ProviderError("invalid_citation", "模型未引用有效教材证据或引用了任务外来源")
    if set(ids) != {s["source_id"] for s in resolve_sources(db, space_id, ids)}:
        raise ProviderError("source_changed", "教材在生成期间发生变化，请重试", 409)
