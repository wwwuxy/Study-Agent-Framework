import fcntl
import hashlib
import json
import os

from fsrs import Card, ReviewLog
from sqlalchemy import select

from app.core.orchestrator import rebuild_states, save_plan
from app.db.models import MaintenanceOperation, ReviewLogRecord, ReviewState, StudySpace, User
from app.learner.parameters import validate_parameter_artifact
from app.main import create_app
from app.maintenance.reset_learning import maintenance_marker
from app.reviews.fsrs_adapter import scheduler


async def rebuild_algorithms(settings, artifact, operation_id):
    bundle = validate_parameter_artifact(artifact)
    if artifact["status"] != "validated":
        raise ValueError("请先验证参数候选，不能直接发布")
    digest = hashlib.sha256(json.dumps(artifact, sort_keys=True).encode()).hexdigest()
    app = create_app(
        settings.model_copy(update={"material_worker_enabled": False, "learner_parameters_path": None})
    )
    app.state.session_factory.configure(info={"algorithm_parameters": bundle})
    marker = maintenance_marker(settings)
    marker.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(marker, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    finished = False
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
            operation = db.get(MaintenanceOperation, operation_id)
            if operation:
                if operation.kind != "rebuild-algorithms" or operation.data["sha256"] != digest:
                    raise ValueError("操作标识已用于其他维护参数")
                if operation.status == "completed":
                    finished = True
                    return operation.data["result"]
            else:
                operation = MaintenanceOperation(
                    id=operation_id,
                    kind="rebuild-algorithms",
                    data={
                        "sha256": digest,
                        "space_ids": list(
                            db.scalars(
                                select(StudySpace.id).where(StudySpace.status.not_in(["deleted", "archived"]))
                            )
                        ),
                        "done": [],
                    },
                )
                db.add(operation)
                db.commit()
            targets = list(operation.data["space_ids"])
        for sid in targets:
            with app.state.session_factory() as db:
                operation = db.get(MaintenanceOperation, operation_id)
                if sid in operation.data["done"]:
                    continue
                space = db.get(StudySpace, sid)
                if space and space.status not in {"deleted", "archived"}:
                    db.scalar(select(User).where(User.id == space.user_id).with_for_update())
                    space = db.scalar(
                        select(StudySpace)
                        .where(StudySpace.id == sid)
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                    await rebuild_states(db, space)
                    for row in db.scalars(select(ReviewState).where(ReviewState.space_id == sid)):
                        records = db.scalars(
                            select(ReviewLogRecord).where(ReviewLogRecord.state_id == row.id)
                        ).all()
                        logs = sorted(
                            [ReviewLog.from_dict(record.log) for record in records],
                            key=lambda r: r.review_datetime,
                        )
                        if logs:
                            card = scheduler(bundle.fsrs).reschedule_card(Card.from_dict(row.card), logs)
                            row.card, row.due = card.to_dict(), card.due
                        row.parameter_version = bundle.fsrs.version
                    db.flush()
                    save_plan(db, space)
                    space.algorithm_versions = {
                        "bkt": "pybkt_v1",
                        "fsrs": "fsrs_v6",
                        "bkt_parameters": bundle.bkt.version,
                        "fsrs_parameters": bundle.fsrs.version,
                    }
                operation.data = {**operation.data, "done": [*operation.data["done"], sid]}
                db.commit()
        with app.state.session_factory() as db:
            operation = db.get(MaintenanceOperation, operation_id)
            result = {
                "operation_id": operation_id,
                "spaces_rebuilt": len(operation.data["done"]),
                "parameters_sha256": digest,
            }
            operation.data = {**operation.data, "result": result}
            operation.status = "completed"
            db.commit()
        finished = True
        return result
    finally:
        if finished:
            marker.unlink(missing_ok=True)
        os.close(fd)
        app.state.engine.dispose()
