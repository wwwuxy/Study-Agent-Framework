"""Content deletion shared by the authenticated API and local maintenance."""

from sqlalchemy import delete, select

from app.db.models import (
    AgentRun,
    AnalysisRun,
    AssessmentAttempt,
    AssessmentItem,
    ChatTurn,
    ConceptPrerequisite,
    DailyPlan,
    DailyTask,
    InboxMessage,
    KnowledgeConcept,
    LearnerConceptState,
    LearningEvent,
    LearningIntent,
    LearningPlan,
    LearningSuggestion,
    Lesson,
    MaterialAsset,
    MaterialJob,
    MaterialSection,
    PeriodicJob,
    PlanRevision,
    ReviewLogRecord,
    ReviewSession,
    ReviewState,
    WeeklySummary,
    new_id,
)
from app.knowledge.materials import new_job


def erase_space_content(db, space, storage):
    if space.status == "deleted":
        return {"id": space.id, "status": "deleted"}
    # A tombstone is required for uploads already in flight to register late handles.
    # All learning content is erased; this marker cannot restore a space.
    from app.activity.tasks import cancel_space_activity
    from app.db.models import utcnow

    cancel_space_activity(db, space, utcnow())
    space.status = "deleted"
    space.goal, space.expected_level, space.request_digest = "", "", ""
    space.provider_id, space.target_date = None, None
    space.daily_minutes, space.allow_general_knowledge = 0, False
    db.flush()
    assets = db.scalars(
        select(MaterialAsset)
        .where(MaterialAsset.space_id == space.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    jobs = db.scalars(select(MaterialJob).where(MaterialJob.space_id == space.id).with_for_update()).all()
    for job in jobs:
        origin = job.data.get("_upload_provider_id")
        if job.status in {"queued", "running", "failed"}:
            job.status = "cancelled"
        job.data = {"_upload_provider_id": origin} if origin and job.lease_until else {}
        job.error_code, job.error_message = None, None
    for asset in assets:
        asset.generation += 1
        asset.status = "deleting"
        asset.filename, asset.sha256, asset.request_digest = "", "", ""
        asset.size_bytes, asset.use_embeddings, asset.warning = 0, False, None
        new_job(db, asset, "space_delete_" + new_id(), "cleanup")
    from app.exam_diagnostics.cleanup import erase_space as erase_exams

    erase_exams(db, space, str(storage.root))
    storage.delete_space(space.user_id, space.id)
    # Dependency order respects both SQLite foreign keys and PostgreSQL/pgvector.
    for model in (
        DailyTask,
        DailyPlan,
        LearningSuggestion,
        InboxMessage,
        WeeklySummary,
        AnalysisRun,
        PeriodicJob,
        PlanRevision,
        ChatTurn,
        LearningIntent,
        ReviewLogRecord,
        ReviewSession,
        ReviewState,
        MaterialSection,
        AssessmentAttempt,
        AssessmentItem,
        Lesson,
        LearningEvent,
        LearnerConceptState,
        ConceptPrerequisite,
        KnowledgeConcept,
        LearningPlan,
        AgentRun,
        AnalysisRun,
        DailyPlan,
        DailyTask,
        InboxMessage,
        LearningSuggestion,
        PeriodicJob,
        WeeklySummary,
        PlanRevision,
        ChatTurn,
        LearningIntent,
    ):
        db.execute(delete(model).where(model.space_id == space.id))
    db.flush()
    return {"id": space.id, "status": "deleted"}
