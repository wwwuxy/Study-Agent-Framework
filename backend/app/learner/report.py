from datetime import timedelta

from starlette.concurrency import run_in_threadpool

from app.core.orchestrator import concept_data, event_data, next_action, profile
from app.learner.evidence import ASSESSMENTS
from app.learner.parameters import ParameterBundle, algorithm_manifest
from app.learner.service import compute_states
from app.reviews.sessions import list_reviews


def fraction(numerator, denominator):
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator if denominator else None,
        "reason": None if denominator else "本窗口没有符合条件的记录",
    }


async def build_report(db, space, days, now):
    events, concepts = event_data(db, space.id), concept_data(db, space.id)
    cutoff = (now - timedelta(days=days)).isoformat()
    recent = [e for e in events if cutoff <= e["occurred_at"] <= now.isoformat()]
    old = await run_in_threadpool(
        compute_states,
        concepts,
        [e for e in events if e["occurred_at"] < cutoff],
        db.info.get("algorithm_parameters", ParameterBundle()).bkt,
    )
    current = profile(db, space)["states"]
    distribution = {
        status: sum(s["status"] == status for s in current) for status in ("unknown", "learning", "mastered")
    }
    answers = [e for e in recent if e["type"] in ASSESSMENTS]
    reviews = [
        e
        for e in answers
        if e["type"] == "review_submitted"
        and e.get("confidence") == "high"
        and isinstance(e.get("is_correct"), bool)
        and not e.get("evaluator", "").startswith("llm_rubric:")
    ]
    starts = {e["lesson_id"] for e in recent if e["type"] == "learning_task_started"}
    completions = {e["lesson_id"] for e in recent if e["type"] == "learning_task_completed"}
    rank = {"unknown": 0, "learning": 1, "mastered": 2}
    names = {c["key"]: c["name"] for c in concepts}
    from datetime import datetime

    from sqlalchemy import func, select

    from app.exam_diagnostics.models import ExamDiagnostic

    imported_count = db.scalar(
        select(func.count())
        .select_from(ExamDiagnostic)
        .where(
            ExamDiagnostic.space_id == space.id,
            ExamDiagnostic.status == "completed",
            ExamDiagnostic.imported_at >= datetime.fromisoformat(cutoff),
            ExamDiagnostic.imported_at <= now,
        )
    )
    imported_evidence = [
        e
        for e in events
        if e["type"] == "exam_question_imported" and cutoff <= e.get("imported_at", "") <= now.isoformat()
    ]
    return {
        "external_imports": {
            "diagnostics": imported_count,
            "effective_evidence": len(imported_evidence),
            "window_basis": "imported_at",
        },
        "study_space_id": space.id,
        "days": days,
        "as_of": now.isoformat(),
        "window_start": cutoff,
        "algorithms": algorithm_manifest(db.info.get("algorithm_parameters")),
        "distribution": distribution,
        "evidence": {
            "answers": len(answers),
            "independent": sum(e.get("assistance_level") == "none" for e in answers),
            "assisted": sum(e.get("assistance_level") != "none" for e in answers),
            "uncertain": sum(e.get("confidence") != "high" or e.get("is_correct") is None for e in answers),
        },
        "progress": [
            {
                "concept_id": s["concept_id"],
                "name": names[s["concept_id"]],
                "before": old[s["concept_id"]]["status"],
                "after": s["status"],
                "improved": rank[s["status"]] > rank[old[s["concept_id"]]["status"]],
            }
            for s in current
        ],
        "misconceptions": list(dict.fromkeys(m for s in current for m in s.get("misconceptions", []))),
        "error_concepts": [
            {
                "concept_id": key,
                "name": name,
                "count": len(wrong),
                "last_occurred_at": wrong[-1]["occurred_at"],
            }
            for key, name in names.items()
            if (
                wrong := [
                    e
                    for e in answers
                    if key in e.get("concept_ids", [])
                    and e.get("is_correct") is False
                    and e.get("confidence") == "high"
                ]
            )
        ],
        "reviews": list_reviews(db, space, now),
        "review_retention": fraction(
            sum(e["is_correct"] and e.get("assistance_level") == "none" for e in reviews), len(reviews)
        ),
        "task_completion": fraction(len(starts & completions), len(starts)),
        "next_action": next_action(db, space, now=now),
        "notice": "报告根据已保存的学习记录汇总。独立回忆率统计所选时间内可确认的复习作答，任务完成率统计同期开始的课堂。掌握估计使用默认参数，仅供学习参考。",
    }
