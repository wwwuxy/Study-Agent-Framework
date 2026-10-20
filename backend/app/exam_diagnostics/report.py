"""Server-derived statistics; never trusts model-generated counters."""

from collections import Counter


def leaves(recognition):
    parents = {q.parent_id for q in recognition.questions if q.parent_id}
    return [q for q in recognition.questions if q.key not in parents]


def summarize(recognition):
    items = leaves(recognition)
    counts = {key: 0 for key in ("correct", "incorrect", "partial", "unanswered", "uncertain")}
    counts.update(Counter(q.result for q in items))
    scored = [q for q in items if q.score is not None]
    summed = sum(q.score for q in scored) if scored else None
    full = bool(items) and all(q.score is not None and q.max_score is not None for q in items)
    denominator = counts["correct"] + counts["incorrect"]
    concepts = {}
    for q in items:
        for key in q.concept_ids:
            value = concepts.setdefault(
                key,
                {
                    "question_ids": [],
                    "correct": 0,
                    "incorrect": 0,
                    "partial": 0,
                    "unanswered": 0,
                    "uncertain": 0,
                },
            )
            value["question_ids"].append(q.key)
            value[q.result] += 1
    return {
        "counts": counts,
        "total_questions": len(items),
        "coverage_complete": recognition.coverage_complete,
        "coverage_note": recognition.coverage_note,
        "verified_score_sum": summed,
        "all_scores_known": full,
        "stated_score": recognition.stated_score,
        "stated_max_score": recognition.stated_max_score,
        "score_conflict": bool(
            full and recognition.stated_score is not None and abs(summed - recognition.stated_score) > 1e-6
        ),
        "correctness_rate": counts["correct"] / denominator
        if denominator and recognition.coverage_complete
        else None,
        "concepts": concepts,
    }
