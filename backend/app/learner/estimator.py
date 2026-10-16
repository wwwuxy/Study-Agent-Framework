ASSESSMENTS = {"diagnostic_submitted", "assessment_submitted", "review_submitted", "practice_completed"}


def estimate(concept_id: str, events: list[dict]) -> dict:
    """Replay immutable evidence; repeated items cannot manufacture mastery."""
    evidence = {}
    for e in events:
        if (
            e["type"] not in ASSESSMENTS
            or concept_id not in e.get("concept_ids", [])
            or e.get("confidence") != "high"
            or e.get("is_correct") is None
        ):
            continue
        if len(e["concept_ids"]) > 1 and not e["is_correct"]:
            continue
        evidence.setdefault(e["assessment_item_id"], e)
    values = list(evidence.values())
    independent = [
        e
        for e in values
        if e["is_correct"]
        and e.get("assistance_level") == "none"
        and e.get("difficulty", 0) >= 2
        and not e.get("evaluator", "").startswith("llm_rubric:")
    ]
    score = sum(
        (1 if e.get("assistance_level") == "none" else 0.35) if e["is_correct"] else 0 for e in values
    )
    mastery = round((1 + score) / (2 + len(values)), 3) if values else None
    recent_error = bool(values and not values[-1]["is_correct"])
    status = "unknown" if not values else "learning"
    if len(independent) >= 2 and mastery >= 0.7 and not recent_error:
        status = "mastered"
    return {
        "status": status,
        "mastery_estimate": mastery,
        "evidence_count": len(values),
        "independent_correct_count": len(independent),
        "evidence_confidence": "high" if len(values) >= 4 else "medium" if len(values) >= 2 else "low",
        "misconceptions": list(dict.fromkeys(m for e in values for m in e.get("misconceptions", []))),
        "estimator_version": "rules_v1",
        "last_assessed_at": values[-1].get("occurred_at") if values else None,
    }
