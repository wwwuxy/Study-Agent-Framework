from app.chat.contracts import ApplicationResult
from app.db.models import (
    ConceptPrerequisite,
    KnowledgeConcept,
    LearnerConceptState,
    LearningIntent,
    PlanRevision,
    new_id,
    utcnow,
)
from app.knowledge.concept_graph import validate_graph
from app.learner.parameters import ParameterBundle
from app.learner.service import compute_states
from app.planning.intent import effective_scope, plan_view, read_intent
from app.providers.base import ProviderError
from app.reviews.state import ensure_memory_states


def apply_decision(db, space, turn, decision):
    from app.core.orchestrator import append_event, concept_data, save_plan

    before = read_intent(db, space)
    if decision.kind != "update_plan":
        return ApplicationResult(
            "clarification_needed" if decision.kind == "clarify" else "not_changed",
            [],
            before,
            before,
            None,
            plan_view(db, space),
        )
    patch = decision.patch.model_dump(mode="json", exclude_unset=True) if decision.patch else {}
    after = {**before, **patch}
    if decision.stages is not None:
        after["stages"] = [s.model_dump() for s in decision.stages]
    existing = concept_data(db, space.id)
    added = [c.model_dump() for c in decision.added_concepts]
    concepts = existing + added
    try:
        validate_graph(concepts)
        keys = {c["key"] for c in concepts}
        for field in ["included_concept_ids", "priority_concept_ids", "deferred_concept_ids"]:
            values = after.get(field) or []
            if len(set(values)) != len(values) or not set(values) <= keys:
                raise ValueError("需求引用了不存在或重复的知识点")
        for stage in after["stages"]:
            if not set(stage["concept_ids"]) <= keys:
                raise ValueError("路线引用未知知识点")
        scope = effective_scope(concepts, after)
        if not scope["included_ids"]:
            raise ValueError("目标范围必须包含可学习知识点")
        if not set(after["priority_concept_ids"]) <= set(scope["included_ids"]):
            raise ValueError("重点必须在当前目标范围内")
    except ValueError as exc:
        raise ProviderError("invalid_plan_change", str(exc), 422) from exc
    changes = [
        {"field": k, "before": before.get(k), "after": v, "reason": decision.reason}
        for k, v in after.items()
        if k != "version" and before.get(k) != v
    ]
    if added:
        changes.append(
            {
                "field": "added_concepts",
                "before": [],
                "after": [c["name"] for c in added],
                "reason": decision.reason,
            }
        )
    if not changes:
        return ApplicationResult("not_changed", [], before, before, None, plan_view(db, space))
    for key in ["goal", "daily_minutes", "target_date", "expected_level"]:
        setattr(space, key, after[key])
    for c in added:
        db.add(KnowledgeConcept(space_id=space.id, key=c["key"], data=c))
    db.flush()
    for c in added:
        for p in c["prerequisites"]:
            db.add(ConceptPrerequisite(space_id=space.id, concept_key=c["key"], prerequisite_key=p))
    states = compute_states(added, [], db.info.get("algorithm_parameters", ParameterBundle()).bkt)
    for c in added:
        db.add(LearnerConceptState(space_id=space.id, concept_id=c["key"], data=states[c["key"]]))
    ensure_memory_states(db, space, utcnow())
    after["version"] = before["version"] + 1
    row = db.get(LearningIntent, space.id)
    if row is None:
        row = LearningIntent(space_id=space.id, user_id=space.user_id)
        db.add(row)
    row.version, row.data = (
        after["version"],
        {
            k: v
            for k, v in after.items()
            if k not in ["version", "goal", "daily_minutes", "target_date", "expected_level"]
        },
    )
    db.flush()
    if decision.interrupt_current:
        from app.teaching.lessons import unfinished_lesson
        from app.teaching.lifecycle import pause_current_lesson

        lesson = unfinished_lesson(db, space)
        from app.core.orchestrator import profile
        from app.planning.intent import priority_targets
        from app.reviews.state import memory_states

        states = {s["concept_id"]: s for s in profile(db, space)["states"]}
        desired = (
            priority_targets(concepts, states, memory_states(db, space, utcnow()), after)
            if after["priority_concept_ids"]
            else set(scope["included_ids"])
        )
        if lesson and not set(lesson.action["concept_ids"]) & desired:
            paused = pause_current_lesson(db, space, reason=decision.reason, turn_id=turn.id)
            if paused:
                changes.append(
                    {"field": "paused_lesson", "before": paused, "after": "paused", "reason": decision.reason}
                )
    revision = PlanRevision(
        id=new_id(),
        user_id=space.user_id,
        space_id=space.id,
        turn_id=turn.id,
        version=after["version"],
        data={"before": before, "after": after, "changes": changes},
    )
    db.add(revision)
    append_event(
        db,
        space,
        "requirements_changed",
        "chat_" + turn.id,
        {
            "turn_id": turn.id,
            "revision_id": revision.id,
            "intent_version": after["version"],
            "fields": [c["field"] for c in changes],
        },
    )
    plan = save_plan(db, space)
    return ApplicationResult("applied", changes, before, after, revision.id, plan)
