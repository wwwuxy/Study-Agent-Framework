"""Delete a diagnostic while retaining immutable evidence and cleanup tombstones."""

from sqlalchemy import delete, select

from app.core.orchestrator import append_event, rebuild_states, save_plan
from app.exam_diagnostics import queries, queue
from app.exam_diagnostics.models import ExamAttachment, ExamJob, ExamQuestion
from app.exam_diagnostics.storage import ExamStorage


async def remove(db, user, space, diagnostic_id):
    row = queries.lock_diagnostic(db, user.id, space.id, diagnostic_id)
    if row.status == "deleted":
        for job in db.scalars(
            select(ExamJob).where(ExamJob.diagnostic_id == row.id, ExamJob.kind == "recognize")
        ):
            queue.enqueue_cleanup(db, job)
        return
    published = row.status == "completed"
    append_event(db, space, "exam_diagnostic_deleted", "exam_delete_" + row.id, {"diagnostic_id": row.id})
    row.status = "deleted"
    row.generation += 1
    row.version += 1
    row.name, row.request_digest, row.data = "", "", {}
    row.exam_date, row.imported_at, row.verified_files_digest = None, None, None
    for job in db.scalars(
        select(ExamJob).where(ExamJob.diagnostic_id == row.id, ExamJob.kind == "recognize").with_for_update()
    ):
        job.status, job.active_space_id = "cancelled", None
        job.error_code, job.error_message = None, None
        job.data = {
            k: v for k, v in job.data.items() if k in {"remote_files", "provider_snapshot", "uploading"}
        }
        if not job.data.get("remote_files") and not job.data.get("uploading"):
            job.data = {}
        queue.enqueue_cleanup(db, job)
    db.execute(delete(ExamQuestion).where(ExamQuestion.diagnostic_id == row.id))
    if published:
        await rebuild_states(db, space)
        save_plan(db, space)
    db.flush()


def erase_local_files(db, user_id, space_id, diagnostic_id, storage_root):
    # Called only after the deletion and state rebuild commit. A failed commit
    # must never erase files from a report whose deletion was rolled back.
    storage = ExamStorage(storage_root)
    for attachment in db.scalars(select(ExamAttachment).where(ExamAttachment.diagnostic_id == diagnostic_id)):
        storage.delete(user_id, space_id, attachment.id)
    db.execute(delete(ExamAttachment).where(ExamAttachment.diagnostic_id == diagnostic_id))
