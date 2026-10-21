from sqlalchemy import select

from app.activity.calendar import local_day
from app.activity.presentation import task_view
from app.activity.queue import guard_claim, lock_space
from app.activity.snapshot import read_snapshot
from app.db.models import DailyPlan, DailyTask
from app.planning.intent import effective_scope
from app.planning.policy import choose_action
from app.schemas.activity import DailyPlanResponse, TaskAllocation, TodayResponse


def build_daily_plan(snapshot, period):
    scope = effective_scope(snapshot.concepts, snapshot.intent)["included_ids"]
    names = {c["key"]: c for c in snapshot.concepts}
    action = choose_action(
        list(snapshot.concepts),
        snapshot.states,
        snapshot.memory,
        list(snapshot.events),
        snapshot.intent["daily_minutes"],
        now=snapshot.now,
        target_date=snapshot.intent.get("target_date"),
        intent=snapshot.intent,
    )
    if snapshot.active_lesson:
        action = snapshot.active_lesson["action"]
    candidates = [dict(action)]
    primary = action["concept_ids"][0]
    for key, memory in sorted(snapshot.memory.items(), key=lambda x: (x[1]["due"], x[0])):
        if memory["status"] != "due" or key not in scope or key == primary:
            continue
        available = all(
            snapshot.states.get(p, {}).get("status") == "mastered" for p in names[key]["prerequisites"]
        )
        candidates.append(
            {
                "action": "REVIEW",
                "concept_ids": [key],
                "estimated_minutes": min(10, snapshot.intent["daily_minutes"]),
                "reason": "FSRS到期，安排独立回忆",
                "blocking_reason": None if available else "前置知识证据不足",
            }
        )
    return {
        "candidates": candidates,
        "budget": snapshot.intent["daily_minutes"],
        "fingerprint": snapshot.fingerprint,
        "scope": scope,
    }


def plan_view(db, plan):
    slots = []
    seen = set()
    for allocation in plan.data.get("allocations", []):
        task = db.get(DailyTask, allocation["task_id"])
        if task and task.space_id == plan.space_id and task.user_id == plan.user_id:
            seen.add(task.id)
            slots.append(
                TaskAllocation(
                    task=task_view(task),
                    allocated_minutes=allocation["minutes"],
                    carried_over=task.plan_id != plan.id,
                )
            )
    backlog = [
        task_view(t)
        for t in db.scalars(
            select(DailyTask).where(
                DailyTask.space_id == plan.space_id,
                DailyTask.plan_id == plan.id,
                DailyTask.status == "pending",
            )
        )
        if t.id not in seen
    ]
    return DailyPlanResponse(
        id=plan.id,
        study_space_id=plan.space_id,
        local_date=plan.local_date,
        timezone=plan.timezone,
        budget_minutes=plan.data["budget"],
        intent_version=plan.data["intent_version"],
        fingerprint=plan.data["fingerprint"],
        as_of=plan.data["as_of"],
        warning=plan.data.get("warning"),
        slots=slots,
        backlog=backlog,
    )


def today_plan(db, user_id, space_id, now):
    from app.api.deps import own_space
    from app.db.models import User

    own_space(db, user_id, space_id)
    user = db.get(User, user_id)
    day = local_day(now, user.timezone)
    plan = db.scalar(select(DailyPlan).where(DailyPlan.space_id == space_id, DailyPlan.local_date == day.key))
    return TodayResponse(
        plan=plan_view(db, plan) if plan else None, reason=None if plan else "今日计划尚未生成，可刷新生成"
    )


def coordinate_day(session_factory, user_id, space_id, now, *, claim=None):
    from app.activity.tasks import refresh_completion

    with session_factory.begin() as db:
        user, space = lock_space(db, user_id, space_id)
        if claim:
            guard_claim(db, claim, now)
        period = local_day(now, user.timezone)
        refresh_completion(db, space, now)
        snapshot = read_snapshot(db, space, now)
        draft = build_daily_plan(snapshot, period)
        plan = db.scalar(
            select(DailyPlan).where(DailyPlan.space_id == space_id, DailyPlan.local_date == period.key)
        )
        if not plan:
            plan = DailyPlan(
                user_id=user_id, space_id=space_id, local_date=period.key, timezone=period.timezone
            )
            db.add(plan)
            db.flush()
        existing = db.scalars(
            select(DailyTask)
            .where(DailyTask.space_id == space_id)
            .order_by(DailyTask.created_at, DailyTask.id)
        ).all()
        for t in existing:
            if t.status == "pending" and t.concept_id not in draft["scope"]:
                t.status, t.active_cycle_key = "superseded", None
            if t.plan_id != plan.id and t.status == "pending":
                t.status, t.active_cycle_key = "postponed", None
        db.flush()
        budget = draft["budget"]
        allocations = []
        for allocation in plan.data.get("allocations", []):
            old = next((t for t in existing if t.id == allocation["task_id"]), None)
            if old and old.status in {"completed", "skipped"}:
                minutes = min(allocation["minutes"], budget) if old.status == "completed" else 0
                allocations.append({"task_id": old.id, "minutes": minutes})
                budget -= minutes
        carry = [t for t in existing if t.status == "in_progress"]
        candidates = [] if carry else draft["candidates"]
        for t in carry[:1]:
            minutes = min(t.estimated_minutes, budget)
            allocations.append({"task_id": t.id, "minutes": minutes})
            budget -= minutes
        for action in candidates:
            concept = action["concept_ids"][0]
            memory = snapshot.memory.get(concept, {})
            cycle = (
                f"{memory.get('id')}:{memory.get('last_review')}" if action["action"] == "REVIEW" else None
            )
            key = f"{period.key}:{action['action']}:{concept}:{cycle or ''}"
            task = next((t for t in existing if t.task_key == key), None)
            # A postponed review keeps one canonical active execution.
            if cycle and any(
                t.active_cycle_key == cycle and t.id != (task.id if task else None) for t in existing
            ):
                continue
            if not task:
                name = next(c["name"] for c in snapshot.concepts if c["key"] == concept)
                task = DailyTask(
                    user_id=user_id,
                    space_id=space_id,
                    plan_id=plan.id,
                    task_key=key,
                    concept_id=concept,
                    action=action["action"],
                    estimated_minutes=min(action.get("estimated_minutes", 15), draft["budget"]),
                    active_cycle_key=cycle,
                    data={
                        "origin_task_id": next(
                            (
                                t.id
                                for t in reversed(existing)
                                if t.concept_id == concept
                                and t.action == action["action"]
                                and t.status == "postponed"
                                and t.plan_id != plan.id
                                and t.data.get("cycle_key") == cycle
                            ),
                            None,
                        ),
                        "name": name,
                        "reason": action["reason"],
                        "cycle_key": cycle,
                        "intent_version": snapshot.intent["version"],
                        "action": action,
                    },
                )
                db.add(task)
                db.flush()
                existing.append(task)
            blocked = action.get("blocking_reason")
            if task.status not in {"pending", "in_progress"}:
                continue
            if not blocked and len(allocations) < 6 and task.estimated_minutes <= budget:
                allocations.append({"task_id": task.id, "minutes": task.estimated_minutes})
                budget -= task.estimated_minutes
            else:
                blocked = blocked or "今日预算已满，待安排"
            task.data = {**task.data, "blocking_reason": blocked, "fingerprint": snapshot.fingerprint}
        plan.data = {
            "allocations": allocations,
            "budget": draft["budget"],
            "fingerprint": snapshot.fingerprint,
            "intent_version": snapshot.intent["version"],
            "as_of": now.isoformat(),
            "warning": period.warning,
        }
        db.flush()
        from app.activity.suggestions import update_suggestions

        update_suggestions(db, space, snapshot, plan, period, now)
        return plan_view(db, plan)
