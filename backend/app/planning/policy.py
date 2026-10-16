def choose_action(concepts: list[dict], states: dict, diagnostic_count: int, available_minutes: int) -> dict:
    available = [
        c for c in concepts if all(states.get(p, {}).get("status") == "mastered" for p in c["prerequisites"])
    ]
    unfinished = [c for c in available if states.get(c["key"], {}).get("status") != "mastered"]
    candidates = unfinished or available
    if not candidates:
        raise ValueError("课程不存在可执行节点")
    # Importance/time affect order, while unmet prerequisites always block a node.
    target = max(candidates, key=lambda c: (c.get("importance", 1), -c.get("minutes", 15)))
    state = states.get(target["key"], {})
    if state.get("status", "unknown") == "unknown" and diagnostic_count < 5:
        action, reason = "DIAGNOSE", "关键知识缺少可靠证据，先完成有限预算内的诊断"
    elif state.get("status", "unknown") == "unknown":
        action, reason = "LEARN_CONCEPT", "诊断预算已用完，先学习已满足前置条件的基础知识"
    elif state.get("misconceptions"):
        action, reason = "REMEDIATE", "测评证据显示存在误区，先修复再继续"
    elif state["status"] == "learning":
        action, reason = "PRACTICE", "已有测评证据但尚未达到两道不同题独立达标的掌握门槛"
    else:
        action, reason = "ASSESS", "当前课程已达到初步掌握门槛，安排迁移测评验证"
    return {
        "action": action,
        "concept_ids": [target["key"]],
        "reason": reason,
        "estimated_minutes": min(available_minutes, target.get("minutes", 15)),
        "requires_followup_assessment": True,
        "evidence": {
            "status": state.get("status", "unknown"),
            "evidence_count": state.get("evidence_count", 0),
            "diagnostic_count": diagnostic_count,
        },
        "policy_version": "policy_v1",
    }
