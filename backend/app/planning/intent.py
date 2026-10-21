"""Persistent user intent, separate from evidence-driven scheduling."""

from app.db.models import LearningIntent, utcnow


def read_intent(db, space):
    row = db.get(LearningIntent, space.id)
    return {
        "version": row.version if row else 0,
        "goal": space.goal,
        "daily_minutes": space.daily_minutes,
        "target_date": space.target_date,
        "expected_level": space.expected_level,
        "included_concept_ids": None,
        "priority_concept_ids": [],
        "deferred_concept_ids": [],
        "teaching_preferences": "",
        "learner_notes": "",
        "stages": [],
        **(row.data if row else {}),
    }


def effective_scope(concepts, intent):
    by_key = {c["key"]: c for c in concepts}
    requested = set(intent.get("included_concept_ids") or by_key) - set(
        intent.get("deferred_concept_ids", [])
    )
    included = set()

    def add(key):
        if key in included or key not in by_key:
            return
        included.add(key)
        for p in by_key[key]["prerequisites"]:
            add(p)

    for key in requested:
        add(key)
    required = included - requested
    return {
        "included_ids": sorted(included),
        "required_prerequisites": sorted(required),
        "explanations": ["保留必要前置：" + ", ".join(sorted(required))] if required else [],
    }


def priority_targets(concepts, states, memory, intent):
    by_key = {c["key"]: c for c in concepts}
    all_mastered = all(states.get(c["key"], {}).get("status") == "mastered" for c in concepts)
    for key in intent.get("priority_concept_ids", []):
        if key in by_key and (
            states.get(key, {}).get("status") != "mastered"
            or memory.get(key, {}).get("status") == "due"
            or all_mastered
        ):
            closure = effective_scope(concepts, {"included_concept_ids": [key]})["included_ids"]
            return {
                p
                for p in closure
                if p == key
                or states.get(p, {}).get("status") != "mastered"
                or memory.get(p, {}).get("status") == "due"
            }
    return set()


def plan_view(db, space, *, now=None):
    from app.core.orchestrator import next_action

    intent = read_intent(db, space)
    action = next_action(db, space, now=now)
    return {
        "next_action": action,
        "tasks": [action],
        "daily_minutes": space.daily_minutes,
        "target_date": space.target_date,
        "version": "policy_v3",
        "intent_version": intent["version"],
        "intent": intent,
        "stages": intent["stages"],
        "as_of": (now or utcnow()).isoformat(),
    }
