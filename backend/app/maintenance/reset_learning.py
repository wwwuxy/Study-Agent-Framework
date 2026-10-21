"""Explicit, resumable reset. Never imported as an automatic startup action."""

import fcntl
import hashlib
import os
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.engine import make_url

from app.db.models import (
    AgentRun,
    MaintenanceOperation,
    MaterialAsset,
    MaterialJob,
    StudySpace,
    User,
    as_utc,
    utcnow,
)
from app.jobs.materials import run_job
from app.knowledge.materials import new_job
from app.knowledge.storage import MaterialStorage
from app.main import create_app
from app.services.space_deletion import erase_space_content


def maintenance_marker(settings):
    return Path(settings.material_storage_dir).resolve() / ".maintenance-lock"


def target_fingerprint(settings):
    url = make_url(settings.database_url).set(password=None)
    if url.drivername.startswith("sqlite"):
        url = url.set(database=str(Path(url.database).resolve()))
    return hashlib.sha256(
        (str(url) + "|" + str(Path(settings.material_storage_dir).resolve())).encode()
    ).hexdigest()


def freeze_reset_targets(db, operation_id):
    existing = db.get(MaintenanceOperation, operation_id)
    if existing:
        if existing.kind != "reset-learning":
            raise ValueError("操作标识已用于其他维护任务")
        return existing
    operation = MaintenanceOperation(
        id=operation_id,
        kind="reset-learning",
        data={
            "space_ids": list(db.scalars(select(StudySpace.id))),
            "run_ids": list(db.scalars(select(AgentRun.id))),
            "erased": [],
            "purged": [],
        },
    )
    db.add(operation)
    db.flush()
    return operation


def purge_clean_tombstone(db, sid):
    space = db.get(StudySpace, sid)
    if not space:
        return True
    if space.status != "deleted":
        return False
    assets = db.scalars(select(MaterialAsset).where(MaterialAsset.space_id == sid)).all()
    jobs = db.scalars(select(MaterialJob).where(MaterialJob.space_id == sid)).all()
    if any(a.remote_files or a.status != "deleted" for a in assets):
        return False
    if any(j.kind == "index" and j.lease_until and as_utc(j.lease_until) > utcnow() for j in jobs):
        return False
    from app.exam_diagnostics.cleanup import purge, purgeable

    if not purgeable(db, sid):
        return False
    purge(db, sid)
    db.execute(delete(MaterialJob).where(MaterialJob.space_id == sid))
    db.execute(delete(MaterialAsset).where(MaterialAsset.space_id == sid))
    db.execute(delete(StudySpace).where(StudySpace.id == sid))
    return True


async def reset_learning(settings, operation_id, *, apply=False, expected_target=None):
    if not operation_id or len(operation_id) > 100:
        raise ValueError("操作标识无效")
    fingerprint = target_fingerprint(settings)
    if apply and expected_target != fingerprint:
        raise ValueError("目标指纹不一致，未执行删除")
    app = create_app(settings.model_copy(update={"material_worker_enabled": False}))
    try:
        with app.state.session_factory() as db:
            if not apply:
                return {
                    "fingerprint": fingerprint,
                    "spaces": len(list(db.scalars(select(StudySpace.id)))),
                    "audit_records": len(list(db.scalars(select(AgentRun.id)))),
                    "apply": False,
                }
        marker = maintenance_marker(settings)
        marker.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(marker, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        finished_local = False
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            owner = os.read(fd, 200).decode().strip()
            if owner and owner != operation_id:
                raise ValueError("另一个维护操作尚未恢复，请先完成原操作")
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, operation_id.encode())
            os.ftruncate(fd, len(operation_id.encode()))
            os.fsync(fd)
            with app.state.session_factory() as db:
                operation = freeze_reset_targets(db, operation_id)
                if operation.status == "completed":
                    finished_local = True
                    return operation.data["result"]
                db.commit()
                target_ids = list(db.get(MaintenanceOperation, operation_id).data["space_ids"])
            for sid in target_ids:
                with app.state.session_factory() as db:
                    row = db.get(StudySpace, sid)
                    if row:
                        db.scalar(select(User).where(User.id == row.user_id).with_for_update())
                        row = db.scalar(
                            select(StudySpace)
                            .where(StudySpace.id == sid)
                            .with_for_update()
                            .execution_options(populate_existing=True)
                        )
                        erase_space_content(db, row, MaterialStorage(settings.material_storage_dir))
                    operation = db.get(MaintenanceOperation, operation_id)
                    operation.data = {
                        **operation.data,
                        "erased": list(dict.fromkeys([*operation.data["erased"], sid])),
                    }
                    db.commit()
            # Run only cleanup tasks; never upload, probe or understand a new file.
            with app.state.session_factory() as db:
                jobs = db.scalars(
                    select(MaterialJob).where(
                        MaterialJob.space_id.in_(target_ids), MaterialJob.kind == "cleanup"
                    )
                ).all()
                retried = {j.data.get("parent_job") for j in jobs}
                cleanup_ids = []
                for job in jobs:
                    if job.status == "failed" and job.id not in retried:
                        child = new_job(
                            db,
                            db.get(MaterialAsset, job.asset_id),
                            "reset_retry_" + job.id,
                            "cleanup",
                            {**job.data, "parent_job": job.id},
                        )
                        cleanup_ids.append(child.id)
                    elif job.status == "queued":
                        cleanup_ids.append(job.id)
                db.commit()
            for jid in cleanup_ids:
                await run_job(app, jid)
            from app.exam_diagnostics.cleanup import maintenance_sweep

            await maintenance_sweep(app, target_ids)
            with app.state.session_factory() as db:
                operation = db.get(MaintenanceOperation, operation_id)
                for run_id in operation.data["run_ids"]:
                    db.execute(delete(AgentRun).where(AgentRun.id == run_id))
                purged = [sid for sid in target_ids if purge_clean_tombstone(db, sid)]
                pending = len(
                    list(db.scalars(select(MaterialAsset.id).where(MaterialAsset.space_id.in_(target_ids))))
                )
                from app.exam_diagnostics.models import ExamJob

                pending += sum(
                    bool(j.data.get("remote_files") or j.data.get("uploading"))
                    for j in db.scalars(
                        select(ExamJob).where(ExamJob.space_id.in_(target_ids), ExamJob.kind == "recognize")
                    )
                )
                result = {
                    "operation_id": operation_id,
                    "fingerprint": fingerprint,
                    "spaces_erased": len(target_ids),
                    "spaces_purged": len(purged),
                    "remote_pending": pending,
                    "status": "completed" if len(purged) == len(target_ids) else "cleanup_pending",
                }
                operation.data = {**operation.data, "purged": purged, "result": result}
                operation.status = result["status"]
                db.commit()
            finished_local = True
            return result
        finally:
            if finished_local:
                marker.unlink(missing_ok=True)
            os.close(fd)
    finally:
        app.state.engine.dispose()
