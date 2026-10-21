"""Explainable policy over BKT skill state and native FSRS due times."""

from datetime import date, datetime

from app.planning.intent import effective_scope, priority_targets


def choose_action(
    concepts, states, review_states, evidence, available_minutes, *, now, target_date=None, intent=None
):
    intent = intent or {}
    scope = effective_scope(concepts, intent)
    concepts = [c for c in concepts if c["key"] in scope["included_ids"]]
    priority = priority_targets(concepts, states, review_states, intent)
    available = [
        c for c in concepts if all(states.get(p, {}).get("status") == "mastered" for p in c["prerequisites"])
    ]
    if not available:
        raise ValueError("课程不存在已满足前置条件的节点")
    diagnostic_count = len(
        {e.get("assessment_item_id") for e in evidence if e["type"] == "diagnostic_submitted"}
    )
    all_mastered = all(states.get(c["key"], {}).get("status") == "mastered" for c in concepts)
    scored = []
    urgent = target_date and 0 <= (date.fromisoformat(target_date) - now.date()).days <= 7
    for concept in available:
        state, memory = states.get(concept["key"], {}), review_states.get(concept["key"], {})
        due = memory.get("status") == "due"
        if state.get("status") == "mastered" and not due and not all_mastered:
            continue
        overdue_days = max(0, (now - datetime.fromisoformat(memory["due"])).days) if due else 0
        parts = {
            "goal_weight": concept.get("importance", 1) * 2,
            "user_priority": 40 if concept["key"] in priority else 0,
            "uncertainty": {"low": 2, "medium": 1, "high": 0}.get(state.get("evidence_confidence"), 2),
            "skill_gap": 2 * (1 - (state.get("mastery_estimate") or 0)),
            "review_due": 3 + min(overdue_days, 7) if due else 0,
            "deadline": concept.get("importance", 1) * 0.25 if urgent else 0,
        }
        scored.append((sum(parts.values()), concept, state, memory, parts))
    _, target, state, memory, parts = sorted(scored, key=lambda x: (-x[0], x[1]["key"]))[0]
    status = state.get("status", "unknown")
    if memory.get("status") == "due":
        action, mode, reason = "REVIEW", "spaced_review", "已有知识点到期需要复习，通过独立回忆巩固记忆"
    elif status == "unknown" and diagnostic_count < 5:
        action, mode, reason = (
            "DIAGNOSE",
            "diagnostic",
            "先用几道诊断题了解关键知识的掌握情况，再安排适合你的学习起点",
        )
    elif status == "unknown":
        action, mode, reason = (
            "LEARN_CONCEPT",
            "first_learning",
            "本轮诊断已结束，先从具备学习基础的知识点开始",
        )
    elif state.get("recent_error") or state.get("misconceptions"):
        action, mode, reason = (
            "REMEDIATE",
            "misconception_repair",
            "近期作答显示这里仍有薄弱之处，先巩固再继续学习",
        )
    elif status == "mastered":
        action, mode, reason = (
            "ASSESS",
            "stage_assessment",
            "当前可学习的知识已初步掌握，通过阶段测评检验理解程度",
        )
    elif (state.get("mastery_estimate") or 0) >= 0.7:
        action, mode, reason = "ASSESS", "transfer_test", "已有作答表明你理解了这些知识，试着在新情境中运用"
    else:
        action, mode, reason = (
            "PRACTICE",
            "targeted_practice",
            "已积累一定作答记录，继续针对性练习，确认能否独立完成",
        )
    return {
        "action": action,
        "teaching_mode": mode,
        "concept_ids": [target["key"]],
        "reason": reason,
        "estimated_minutes": min(available_minutes, target.get("minutes", 15)),
        "requires_followup_assessment": True,
        "score_breakdown": parts,
        "evidence": {
            "status": status,
            "evidence_count": state.get("evidence_count", 0),
            "diagnostic_count": diagnostic_count,
            "memory_status": memory.get("status", "unassessed"),
        },
        "policy_version": "policy_v3",
        "scope_explanations": scope["explanations"],
    }
