"""Durable bounded jobs. Each remote call is followed by a lease/generation check."""

import asyncio
import logging
import time
from datetime import timedelta
from types import SimpleNamespace

from pydantic import ValidationError
from sqlalchemy import delete, or_, select, update
from starlette.concurrency import run_in_threadpool

from app.core.orchestrator import get_adapter, rebuild_states, save_plan
from app.db.models import (
    AgentRun,
    KnowledgeConcept,
    MaterialAsset,
    MaterialJob,
    MaterialSection,
    ProviderConfig,
    StudySpace,
    User,
    as_utc,
    new_id,
    utcnow,
)
from app.knowledge.materials import fingerprint, inflight_indexes, new_job
from app.knowledge.storage import MaterialStorage
from app.knowledge.vectors import store_vectors
from app.providers.base import ProviderError
from app.schemas.materials import RemoteOutline, RemoteSection

logger = logging.getLogger("uvicorn.error.study_agent")


async def remote(request, db, config, space_id, step, operation):
    request.app.state.limiter.check(
        "model:" + config.user_id, request.app.state.settings.provider_calls_per_minute
    )
    start = time.monotonic()
    adapter = get_adapter(request, config)
    error = None
    try:
        result = await asyncio.wait_for(operation(adapter), timeout=90)
        schema = {"material_outline": RemoteOutline, "material_section": RemoteSection}.get(step)
        if schema:
            result = schema.model_validate(result).model_dump()
    except TimeoutError:
        error = ProviderError("provider_timeout", "远端资料任务超过时限，可重试")
    except (ValueError, TypeError, ValidationError):
        error = ProviderError("invalid_structured_output", "远端资料内容未通过结构校验")
    except ProviderError as exc:
        error = exc
    # Serialize audit publication with permanent deletion; never recreate learning
    # records after the user has erased a space.
    db.scalar(select(User).where(User.id == config.user_id).with_for_update())
    retained = db.scalar(
        select(StudySpace)
        .where(StudySpace.id == space_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if retained and retained.status != "deleted":
        db.add(
            AgentRun(
                user_id=config.user_id,
                provider_id=config.id,
                space_id=space_id,
                model=config.embedding_model if step == "material_embedding" else config.chat_model,
                step=step,
                elapsed_ms=int((time.monotonic() - start) * 1000),
                usage=adapter.usage,
                error_code=error.code if error else None,
            )
        )
    db.commit()
    if error:
        raise error
    return result


def guard(db, job_id, token):
    db.expire_all()
    job = db.get(MaterialJob, job_id)
    asset = db.get(MaterialAsset, job.asset_id)
    if (
        job.status != "running"
        or job.data.get("_lease") != token
        or (
            job.kind == "index"
            and (
                asset.generation != job.generation
                or asset.status in {"deleting", "deleted", "cancelled"}
                or db.get(StudySpace, asset.space_id).status in {"archived", "deleted"}
            )
        )
    ):
        raise ProviderError("job_cancelled", "任务已取消或被新版本取代", 409)
    if job.kind == "index":
        updated = db.execute(
            update(MaterialAsset)
            .where(
                MaterialAsset.id == asset.id,
                MaterialAsset.generation == job.generation,
                MaterialAsset.status.not_in(["deleting", "deleted", "cancelled"]),
            )
            .values(status="indexing")
        )
        if not updated.rowcount:
            raise ProviderError("job_cancelled", "任务已取消或被新版本取代", 409)
    job.lease_until = utcnow() + timedelta(seconds=120)
    db.commit()
    return job, asset


def config_for(db, asset, lock=False):
    query = select(ProviderConfig).where(ProviderConfig.id == asset.provider_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    config = db.scalar(query)
    if not config or fingerprint(config) != asset.provider_fingerprint:
        raise ProviderError(
            "provider_config_changed", "原模型凭证或模型已变更，请恢复配置清理远端文件，或重新索引", 409
        )
    if not config.tested:
        raise ProviderError("provider_not_tested", "请先重新检测模型能力", 422)
    return config


def checkpoint(db, job, stage, progress, **values):
    token = job.data.get("_lease")
    job = db.scalar(
        select(MaterialJob)
        .where(MaterialJob.id == job.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if job.status != "running" or job.data.get("_lease") != token:
        raise ProviderError("job_cancelled", "任务在保存进度前已取消或替换", 409)
    job.data = {**job.data, **values}
    job.stage, job.progress = stage, progress
    db.commit()


async def sync_concepts(db, asset, sections):
    # Sources enrich knowledge; only answer events may establish mastery.
    existing = db.scalars(select(KnowledgeConcept).where(KnowledgeConcept.space_id == asset.space_id)).all()
    by_name = {c.data["name"]: c for c in existing}
    for section in sections:
        for name in section.data["concepts"]:
            concept = by_name.get(name)
            if concept:
                data = {**concept.data}
            else:
                import hashlib

                key = "mat_" + hashlib.sha256(name.encode()).hexdigest()[:24]
                data = {
                    "key": key,
                    "name": name[:160],
                    "module": section.data["heading"][:160],
                    "objectives": ["解释并应用" + name[:100]],
                    "prerequisites": [],
                    "importance": 1,
                    "minutes": 15,
                }
                concept = KnowledgeConcept(space_id=asset.space_id, key=key, data=data)
                db.add(concept)
                by_name[name] = concept
            data["source_status"] = "user_material_derived"
            data["source_ids"] = list(dict.fromkeys([*data.get("source_ids", []), section.id]))
            concept.data = data
    db.flush()
    space = db.get(StudySpace, asset.space_id)
    await rebuild_states(db, space)
    save_plan(db, space)


def detach_sources(db, space_id, source_ids):
    for concept in db.scalars(select(KnowledgeConcept).where(KnowledgeConcept.space_id == space_id)).all():
        if set(concept.data.get("source_ids", [])) & set(source_ids):
            remaining = [i for i in concept.data["source_ids"] if i not in source_ids]
            concept.data = {
                **concept.data,
                "source_ids": remaining,
                "source_status": "user_material_derived" if remaining else "source_removed_unverified",
            }


async def execute_index(request, db, job_id, token):
    settings = request.app.state.settings
    job, asset = guard(db, job_id, token)
    config = config_for(db, asset)
    if not config.capabilities.get("file_input"):
        raise ProviderError("capability_not_supported", "当前配置没有已验证的 PDF 文件能力", 422)
    if not job.data.get("remote_ref"):
        # Pair with remove_provider's lock so the origin is recorded before a
        # credential can be removed, even if the space changes providers.
        config = config_for(db, asset, lock=True)
        origin_fingerprint = fingerprint(config)
        checkpoint(db, job, "upload", 0, _upload_provider_id=config.id)
        with MaterialStorage(settings.material_storage_dir).open(
            asset.user_id, asset.space_id, asset.id
        ) as file:
            ref = await remote(
                request,
                db,
                config,
                asset.space_id,
                "material_upload",
                lambda adapter: adapter.upload_file(file, asset.filename),
            )
        # Persist handles even if cancellation happened during the network call.
        asset = db.scalar(
            select(MaterialAsset)
            .where(MaterialAsset.id == asset.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if asset.status == "deleted":
            asset.status = "deleting"
        asset.remote_files = [
            *asset.remote_files,
            {"ref": ref, "provider_id": config.id, "fingerprint": origin_fingerprint},
        ]
        db.commit()
        try:
            job, asset = guard(db, job_id, token)
        except ProviderError:
            new_job(
                db,
                asset,
                "cleanup_" + new_id(),
                "cleanup",
                {"handles": [{"ref": ref, "provider_id": config.id, "fingerprint": origin_fingerprint}]},
            )
            db.commit()
            raise
        checkpoint(db, job, "outline", 10, remote_ref=ref)
    ref = job.data["remote_ref"]
    if not job.data.get("outline"):
        config = config_for(db, asset)
        outline = await remote(
            request,
            db,
            config,
            asset.space_id,
            "material_outline",
            lambda adapter: adapter.analyze_file(
                ref,
                {
                    "task": "提取文档标题和章节目录。分节粒度适合学习，section_id 唯一，最多 "
                    + str(settings.material_max_sections)
                    + " 节。不要推测缺失章节。",
                    "schema": RemoteOutline.model_json_schema(),
                },
            ),
        )
        outline = RemoteOutline.model_validate(outline)
        if len(outline.sections) > settings.material_max_sections:
            raise ProviderError("too_many_sections", "章节超过本实例处理上限，请拆分文档后重试", 422)
        job, asset = guard(db, job_id, token)
        checkpoint(db, job, "sections", 20, outline=outline.model_dump(), sections={})
    outline = RemoteOutline.model_validate(job.data["outline"])
    for index, chapter in enumerate(outline.sections):
        job, asset = guard(db, job_id, token)
        config = config_for(db, asset)
        if chapter.section_id in job.data.get("sections", {}):
            continue
        section = await remote(
            request,
            db,
            config,
            asset.space_id,
            "material_section",
            lambda adapter, chapter=chapter: adapter.analyze_file(
                ref,
                {
                    "task": "仅理解指定章节：摘要、关键词、知识点。无法确认的内容不编造。",
                    "section": chapter.model_dump(),
                    "schema": RemoteSection.model_json_schema(),
                },
            ),
        )
        section = RemoteSection.model_validate(section)
        if section.section_id != chapter.section_id:
            raise ProviderError("invalid_section", "模型返回了其他章节，索引已停止")
        # This adapter cannot verify page anchors. Discard model-invented page numbers.
        value = {
            **section.model_dump(),
            "locator": {"chapter": chapter.heading, "page": None},
            "locator_verified": False,
            "is_demo": config.provider_type == "fake_files",
        }
        job, asset = guard(db, job_id, token)
        checkpoint(
            db,
            job,
            "sections",
            20 + int(55 * (index + 1) / len(outline.sections)),
            sections={**job.data.get("sections", {}), chapter.section_id: value},
        )
    vectors = None
    if asset.use_embeddings:
        job, asset = guard(db, job_id, token)
        config = config_for(db, asset)
        if not config.capabilities.get("embedding"):
            raise ProviderError("capability_not_supported", "未验证远端 Embedding 能力", 422)
        if not job.data.get("vectors"):
            texts = [job.data["sections"][c.section_id]["summary"] for c in outline.sections]
            vectors = await remote(
                request,
                db,
                config,
                asset.space_id,
                "material_embedding",
                lambda adapter: adapter.embed_texts(texts),
            )
            job, asset = guard(db, job_id, token)
            checkpoint(db, job, "publish", 90, vectors=vectors)
        vectors = job.data["vectors"]
    job, asset = guard(db, job_id, token)
    config_for(db, asset)
    db.scalar(select(User).where(User.id == asset.user_id).with_for_update())
    space = db.scalar(
        select(StudySpace)
        .where(StudySpace.id == asset.space_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if space.status in {"archived", "deleted"}:
        raise ProviderError("job_cancelled", "学习空间已删除或移除", 409)
    # Lock space, asset, then job (same order as permanent deletion), and atomically
    # verify both generation and lease before publishing. A second process cannot resurrect it.
    changed = db.execute(
        update(MaterialAsset)
        .where(
            MaterialAsset.id == asset.id,
            MaterialAsset.generation == job.generation,
            MaterialAsset.status.not_in(["deleting", "deleted", "cancelled"]),
        )
        .values(status="indexing")
    )
    owned = db.execute(
        update(MaterialJob)
        .where(
            MaterialJob.id == job.id,
            MaterialJob.status == "running",
            MaterialJob.data["_lease"].as_string() == token,
        )
        .values(stage="publish")
    )
    if not changed.rowcount or not owned.rowcount:
        raise ProviderError("job_cancelled", "任务在发布前被取消或替换", 409)
    old_ids = db.scalars(select(MaterialSection.id).where(MaterialSection.asset_id == asset.id)).all()
    detach_sources(db, asset.space_id, old_ids)
    db.execute(delete(MaterialSection).where(MaterialSection.asset_id == asset.id))
    sections = []
    for index, chapter in enumerate(outline.sections):
        row = MaterialSection(
            id=new_id(),
            user_id=asset.user_id,
            space_id=asset.space_id,
            asset_id=asset.id,
            section_key=chapter.section_id,
            data=job.data["sections"][chapter.section_id],
            embedding=vectors[index] if vectors else None,
            embedding_fingerprint=asset.provider_fingerprint if vectors else None,
        )
        db.add(row)
        sections.append(row)
    await sync_concepts(db, asset, sections)
    store_vectors(db, sections, settings.pgvector_enabled)
    asset.status = "ready"
    job.status, job.stage, job.progress = "succeeded", "complete", 100
    # Parsed content remains only in sections; job checkpoints are no longer necessary.
    job.data = {k: v for k, v in job.data.items() if k in {"_lease", "request_digest", "parent_job"}}
    db.commit()


async def execute_cleanup(request, db, job_id, token):
    job, asset = guard(db, job_id, token)
    for handle in list(job.data.get("handles", asset.remote_files)):
        job, asset = guard(db, job_id, token)
        config = db.get(ProviderConfig, handle["provider_id"])
        if not config or fingerprint(config) != handle["fingerprint"]:
            raise ProviderError(
                "remote_cleanup_required", "远端文件仍可能保留；原凭证已变更，请在服务商控制台删除", 409
            )
        await remote(
            request,
            db,
            config,
            asset.space_id,
            "material_delete",
            lambda adapter, handle=handle: adapter.delete_file(handle["ref"]),
        )
        job, asset = guard(db, job_id, token)
        asset.remote_files = [h for h in asset.remote_files if h != handle]
        db.commit()
    job, asset = guard(db, job_id, token)
    uploads = db.scalars(inflight_indexes().where(MaterialJob.asset_id == asset.id)).all()
    if asset.status == "deleting" and not asset.remote_files and uploads:
        # Persist a delayed continuation. Even if the cancelled uploader crashes,
        # lease expiry will make this cleanup runnable again after restart.
        job.status, job.stage, job.progress = "running", "waiting_upload", 95
        job.lease_until = max(as_utc(upload.lease_until) for upload in uploads)
        job.attempts = max(0, job.attempts - 1)
        job.data = {k: v for k, v in job.data.items() if k in {"parent_job", "request_digest"}}
        db.commit()
        return
    if asset.status == "deleting" and not asset.remote_files:
        asset.status = "deleted"
    asset.warning = (
        "仍有远端文件待清理，请检查失败的清理任务"
        if asset.status == "deleting" and asset.remote_files
        else None
    )
    job.status, job.stage, job.progress = "succeeded", "complete", 100
    job.data = {k: v for k, v in job.data.items() if k in {"parent_job", "request_digest"}}
    db.commit()


async def run_job(app, job_id):
    # A job owns its Session and event loop in one worker thread. Synchronous
    # database lock waits must never prevent an ASGI answer from committing.
    await run_in_threadpool(_run_job_in_thread, app, job_id)


def _run_job_in_thread(app, job_id):
    asyncio.run(_run_job(app, job_id))


async def _run_job(app, job_id):
    token = new_id()
    with app.state.session_factory() as db:
        # Atomic claim also works on SQLite; expired leases allow crash recovery.
        claimed = db.execute(
            update(MaterialJob)
            .where(
                MaterialJob.id == job_id,
                or_(
                    MaterialJob.status == "queued",
                    (MaterialJob.status == "running") & (MaterialJob.lease_until < utcnow()),
                ),
                MaterialJob.attempts < app.state.settings.material_job_attempts,
            )
            .values(status="running", lease_until=utcnow() + timedelta(seconds=120))
        )
        if not claimed.rowcount:
            db.rollback()
            job = db.get(MaterialJob, job_id)
            if (
                job
                and job.status == "running"
                and job.lease_until
                and as_utc(job.lease_until) < utcnow()
                and job.attempts >= app.state.settings.material_job_attempts
            ):
                asset = db.get(MaterialAsset, job.asset_id)
                if (
                    job.kind == "index"
                    and asset.generation == job.generation
                    and asset.status not in {"deleted", "deleting", "cancelled"}
                ):
                    asset.status = "failed"
                job.status, job.error_code, job.error_message = (
                    "failed",
                    "job_attempts_exhausted",
                    "任务多次被中断，已停止自动恢复；请检查后手动重试",
                )
                asset = db.get(MaterialAsset, job.asset_id)
                if (
                    job.kind == "index"
                    and asset.generation == job.generation
                    and asset.status not in {"deleted", "deleting", "cancelled"}
                ):
                    asset.status = "failed"
                db.commit()
            return
        job = db.get(MaterialJob, job_id)
        job.attempts += 1
        job.data = {**job.data, "_lease": token}
        db.commit()
        request = SimpleNamespace(app=app)
        try:
            if job.kind == "index":
                await execute_index(request, db, job_id, token)
            else:
                await execute_cleanup(request, db, job_id, token)
        except ProviderError as exc:
            db.rollback()
            job = db.get(MaterialJob, job_id)
            asset = db.get(MaterialAsset, job.asset_id)
            if job.status == "running" and job.data.get("_lease") == token:
                job.status = "cancelled" if exc.code == "job_cancelled" else "failed"
                job.error_code, job.error_message = exc.code, exc.message
                if (
                    job.kind == "index"
                    and asset.generation == job.generation
                    and asset.status not in {"deleting", "deleted", "cancelled"}
                ):
                    asset.status = "failed"
                if job.kind == "cleanup":
                    asset.warning = exc.message
                db.commit()
        except Exception as exc:
            db.rollback()
            logger.error("material_job_failed job_id=%s type=%s", job_id, type(exc).__name__)
            job = db.get(MaterialJob, job_id)
            if job.status == "running" and job.data.get("_lease") == token:
                asset = db.get(MaterialAsset, job.asset_id)
                if (
                    job.kind == "index"
                    and asset.generation == job.generation
                    and asset.status not in {"deleted", "deleting", "cancelled"}
                ):
                    asset.status = "failed"
                job.status, job.error_code, job.error_message = (
                    "failed",
                    "job_failed",
                    "资料任务失败，可查看服务端日志后重试",
                )
                db.commit()
        finally:
            db.rollback()
            job = db.get(MaterialJob, job_id)
            if job and job.kind == "index" and job.status == "cancelled":
                job.lease_until = None
                job.data = {}
                db.flush()
                asset = db.get(MaterialAsset, job.asset_id)
                if (
                    db.get(StudySpace, asset.space_id).status == "deleted"
                    and not asset.remote_files
                    and not db.scalar(inflight_indexes().where(MaterialJob.asset_id == asset.id))
                ):
                    asset.status, asset.warning = "deleted", None
                db.commit()


async def worker(app):
    while True:
        try:
            from pathlib import Path

            if (Path(app.state.settings.material_storage_dir) / ".maintenance-lock").exists():
                await asyncio.sleep(1)
                continue
            with app.state.session_factory() as db:
                jobs = db.scalars(
                    select(MaterialJob.id)
                    .where(
                        or_(
                            MaterialJob.status == "queued",
                            (MaterialJob.status == "running") & (MaterialJob.lease_until < utcnow()),
                        )
                    )
                    .order_by(MaterialJob.created_at)
                    .limit(1)
                ).all()
            for job_id in jobs:
                await run_job(app, job_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("material_worker_poll_failed type=%s", type(exc).__name__)
        await asyncio.sleep(1)
