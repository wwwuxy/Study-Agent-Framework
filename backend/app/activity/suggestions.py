from datetime import date, datetime

from sqlalchemy import select

from app.activity.calendar import local_day, zone
from app.activity.inbox import put_message
from app.activity.snapshot import read_snapshot
from app.db.models import DailyPlan, DailyTask, LearningSuggestion, User, as_utc
from app.planning.intent import effective_scope
from app.providers.base import ProviderError
from app.schemas.activity import SuggestionResponse


def suggestion_view(row):
    return SuggestionResponse(
        id=row.id,
        study_space_id=row.space_id,
        status=row.status,
        kind=row.data["kind"],
        title=row.data["title"],
        reason=row.data["reason"],
        fingerprint=row.data["fingerprint"],
        created_at=as_utc(row.created_at).isoformat(),
    )


def derive_suggestions(snapshot, period):
    tz, _ = zone(period.timezone)
    day = date.fromisoformat(period.key)
    events = [
        e
        for e in snapshot.events
        if e["type"] in {"lesson_viewed", "diagnostic_submitted", "assessment_submitted", "review_submitted"}
        and datetime.fromisoformat(e["occurred_at"]) <= snapshot.now
    ]
    result = []
    if events:
        latest = max(datetime.fromisoformat(e["occurred_at"]).astimezone(tz).date() for e in events)
        days = (day - latest).days
        if days >= 3:
            result.append(
                {
                    "kind": "interruption",
                    "title": "从一项小任务重新开始",
                    "reason": f"距最近学习已有{days}个当地日期；先继续一项任务。",
                }
            )
    scope = effective_scope(snapshot.concepts, snapshot.intent)["included_ids"]
    predecessors = {t.get("origin_task_id") for t in snapshot.tasks if t.get("origin_task_id")}
    old = [
        t
        for t in snapshot.tasks
        if t["status"] in {"pending", "postponed"}
        and t["id"] not in predecessors
        and t["concept_id"] in scope
        and datetime.fromisoformat(t["created_at"]).astimezone(tz).date() < day
    ]
    due = [key for key, value in snapshot.memory.items() if value["status"] == "due" and key in scope]
    if (
        len(old) >= 2
        or len(due) * min(10, snapshot.intent["daily_minutes"]) > snapshot.intent["daily_minutes"]
    ):
        result.append(
            {
                "kind": "overload",
                "title": "把积压任务分成几天",
                "reason": f"{len(old)}项历史未完成安排、{len(due)}项到期复习；可将未开始项目减量或改期。",
            }
        )
    target = snapshot.intent.get("target_date")
    late = False
    if target:
        from app.activity.calendar import previous_week
        from app.activity.weekly import forecast_snapshot

        forecast = forecast_snapshot(snapshot, previous_week(snapshot.now, period.timezone))
        late = bool(forecast.latest and forecast.latest > target)
    if (
        target
        and (date.fromisoformat(target) < day or late)
        and any(snapshot.states.get(k, {}).get("status") != "mastered" for k in scope)
    ):
        result.append(
            {
                "kind": "deadline",
                "title": "重新检查目标排期",
                "reason": (
                    "目标日期已过" if date.fromisoformat(target) < day else "按已观察速度估计可能超过目标日期"
                )
                + "，当前范围尚未达标；可先整理待办，通过学习对话修改目标日期。",
            }
        )
    return result


def update_suggestions(db, space, snapshot, plan, period, now):
    candidates = derive_suggestions(snapshot, period)
    for row in db.scalars(
        select(LearningSuggestion).where(
            LearningSuggestion.space_id == space.id, LearningSuggestion.status == "pending"
        )
    ):
        if (
            row.data["fingerprint"] != snapshot.fingerprint
            or row.data.get("period") != period.key
            or row.data["kind"] not in {c["kind"] for c in candidates}
        ):
            row.status = "expired"
    for item in candidates:
        key = f"{period.key}:{item['kind']}:{snapshot.fingerprint[:16]}"
        row = db.scalar(
            select(LearningSuggestion).where(
                LearningSuggestion.space_id == space.id, LearningSuggestion.event_key == key
            )
        )
        if not row:
            row = LearningSuggestion(
                user_id=space.user_id,
                space_id=space.id,
                event_key=key,
                data={**item, "fingerprint": snapshot.fingerprint, "period": period.key},
                created_at=now,
            )
            db.add(row)
            db.flush()
            put_message(
                db, space, f"deviation:{item['kind']}:{period.key}", "deviation", row.id, item["reason"], now
            )
    scope = effective_scope(snapshot.concepts, snapshot.intent)["included_ids"]
    due = sum(v["status"] == "due" and k in scope for k, v in snapshot.memory.items())
    if due:
        put_message(
            db,
            space,
            f"due:{period.key}",
            "due",
            plan.id,
            f"{due}项复习已到期，今日安排受预算与前置知识限制。",
            now,
        )


def apply_suggestion(db, space, suggestion_id, decision, now):
    row = db.scalar(
        select(LearningSuggestion)
        .where(
            LearningSuggestion.id == suggestion_id,
            LearningSuggestion.space_id == space.id,
            LearningSuggestion.user_id == space.user_id,
        )
        .with_for_update()
    )
    if not row:
        raise ProviderError("not_found", "建议不存在", 404)
    target = "accepted" if decision == "accept" else "skipped"
    if row.status == target:
        return suggestion_view(row)
    snapshot = read_snapshot(db, space, now)
    period = local_day(now, db.get(User, space.user_id).timezone)
    if (
        row.status != "pending"
        or row.data["fingerprint"] != snapshot.fingerprint
        or row.data.get("period") != period.key
        or row.data["kind"] not in {c["kind"] for c in derive_suggestions(snapshot, period)}
    ):
        raise ProviderError("suggestion_changed", "建议所依据的学习状态已改变，请刷新", 409)
    if decision == "accept" and row.data["kind"] in {"overload", "deadline"}:
        plan = db.scalar(
            select(DailyPlan).where(DailyPlan.space_id == space.id, DailyPlan.local_date == period.key)
        )
        if plan:
            keep = []
            kept_pending = False
            for slot in plan.data.get("allocations", []):
                task = db.get(DailyTask, slot["task_id"])
                if task.status == "pending" and kept_pending:
                    from app.activity.tasks import set_task_disposition

                    set_task_disposition(db, space, task.id, "postponed", now)
                else:
                    keep.append(slot)
                    kept_pending = kept_pending or task.status == "pending"
            plan.data = {**plan.data, "allocations": keep}
    row.status = target
    return suggestion_view(row)
