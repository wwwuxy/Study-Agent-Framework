from sqlalchemy import select

from app.activity.contracts import ActivitySnapshot
from app.activity.presentation import task_view
from app.core.orchestrator import concept_data, digest, event_data, profile
from app.db.models import DailyTask
from app.learner.parameters import ParameterBundle
from app.planning.intent import read_intent
from app.reviews.state import memory_states
from app.teaching.lessons import unfinished_lesson


def read_snapshot(db, space, now):
    intent = read_intent(db, space)
    concepts = concept_data(db, space.id)
    states = {s["concept_id"]: s for s in profile(db, space)["states"]}
    memory = memory_states(db, space, now)
    lesson = unfinished_lesson(db, space)
    active = {"id": lesson.id, "action": lesson.action, "completed": lesson.completed} if lesson else None
    fingerprint = digest(
        {
            "intent": intent,
            "algorithms": space.algorithm_versions,
            "concepts": concepts,
            "states": states,
            "memory": {k: {f: v.get(f) for f in ("status", "due", "last_review")} for k, v in memory.items()},
            "lesson": active,
        }
    )
    tasks = tuple(
        task_view(t).model_dump()
        | {
            "cycle_key": t.data.get("cycle_key"),
            "origin_task_id": t.data.get("origin_task_id"),
            "postponed_until": t.data.get("postponed_until"),
            "started_at": t.data.get("started_at"),
            "completed_at": t.data.get("completed_at"),
            "disposed_at": t.data.get("disposed_at"),
        }
        for t in db.scalars(select(DailyTask).where(DailyTask.space_id == space.id))
    )
    return ActivitySnapshot(
        space.user_id,
        space.id,
        now,
        intent,
        tuple(concepts),
        states,
        memory,
        tuple(event_data(db, space.id)),
        active,
        tasks,
        fingerprint,
        db.info.get("algorithm_parameters", ParameterBundle()).bkt,
    )
