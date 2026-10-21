from datetime import datetime

from sqlalchemy import select

from app.db.models import KnowledgeConcept, ReviewLogRecord, ReviewState, as_utc
from app.learner.evidence import observations_for
from app.learner.parameters import ParameterBundle
from app.providers.base import ProviderError
from app.reviews.fsrs_adapter import memory_view, new_card, review_card


def ensure_memory_states(db, space, now):
    existing = set(db.scalars(select(ReviewState.concept_id).where(ReviewState.space_id == space.id)))
    for key in db.scalars(select(KnowledgeConcept.key).where(KnowledgeConcept.space_id == space.id)):
        if key not in existing:
            db.add(
                ReviewState(
                    user_id=space.user_id,
                    space_id=space.id,
                    concept_id=key,
                    card=new_card(now),
                    due=now,
                    parameter_version=db.info.get("algorithm_parameters", ParameterBundle()).fsrs.version,
                )
            )
    db.flush()


def apply_memory_event(db, space, event):
    if event.type == "exam_question_imported":
        return None
    values = {
        **event.data,
        "type": event.type,
        "event_id": event.id,
        "occurred_at": as_utc(event.occurred_at).isoformat(),
    }
    concepts = values.get("concept_ids", [])
    if len(concepts) != 1 or not observations_for(concepts[0], [values]).observations:
        return None
    previous = db.scalar(select(ReviewLogRecord).where(ReviewLogRecord.event_id == event.id))
    if previous:
        return {"rating": previous.log["rating"], "due": previous.after["due"]}
    state = db.scalar(
        select(ReviewState)
        .where(
            ReviewState.space_id == space.id,
            ReviewState.user_id == space.user_id,
            ReviewState.concept_id == concepts[0],
        )
        .with_for_update()
    )
    configuration = db.info.get("algorithm_parameters", ParameterBundle()).fsrs
    if state.parameter_version != configuration.version:
        raise ProviderError("state_rebuild_required", "FSRS 参数已变更，请先重建复习状态", 409)
    requested = values.get("memory_rating")
    independent_correct = values["is_correct"] and values.get("assistance_level") == "none"
    ratings = {"again": 1, "hard": 2, "good": 3, "easy": 4}
    if requested and (
        (not independent_correct and requested != "again") or (independent_correct and requested == "again")
    ):
        raise ProviderError(
            "invalid_memory_rating", "回忆难度与独立作答证据不一致；使用提示或答错只能记为未独立回忆", 422
        )
    rating = ratings.get(requested, 3 if independent_correct else 1)
    duration = values.get("duration_seconds")
    result = review_card(
        state.card,
        rating,
        as_utc(event.occurred_at),
        duration * 1000 if duration is not None else None,
        configuration=configuration,
    )
    db.add(
        ReviewLogRecord(
            user_id=space.user_id,
            space_id=space.id,
            state_id=state.id,
            event_id=event.id,
            log=result.log,
            before=state.card,
            after=result.card,
            parameter_version=state.parameter_version,
        )
    )
    state.card, state.due = result.card, datetime.fromisoformat(result.card["due"])
    return {
        "rating": rating,
        "reason": "独立回忆" if independent_correct else "尚未独立回忆",
        "due": result.card["due"],
        "state": memory_view(result.card, as_utc(event.occurred_at), configuration)["state"],
    }


def memory_states(db, space, now):
    configuration = db.info.get("algorithm_parameters", ParameterBundle()).fsrs
    rows = list(
        db.scalars(
            select(ReviewState).where(ReviewState.space_id == space.id, ReviewState.user_id == space.user_id)
        )
    )
    if any(row.parameter_version != configuration.version for row in rows):
        raise ProviderError("state_rebuild_required", "FSRS 参数已变更，请先重建复习状态", 409)
    return {
        row.concept_id: {
            "id": row.id,
            "concept_id": row.concept_id,
            **memory_view(row.card, now, configuration),
        }
        for row in rows
    }
