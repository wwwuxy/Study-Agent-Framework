import math
from datetime import datetime, timedelta

from sqlalchemy import select

from app.activity.calendar import period as make_period
from app.activity.calendar import zone
from app.activity.inbox import put_message
from app.activity.queue import guard_claim, lock_space
from app.activity.snapshot import read_snapshot
from app.db.models import WeeklySummary
from app.learner.evidence import ASSESSMENTS, observations_for
from app.learner.report import fraction
from app.learner.service import compute_states
from app.planning.intent import effective_scope
from app.schemas.activity import GoalForecast, WeeklySummaryResponse


def forecast_goal(remaining, complete_week_gains, as_of, target_date):
    values = list(complete_week_gains)
    common = {
        "remaining_concepts": remaining,
        "target_date": target_date,
        "sample_weeks": len(values),
        "weekly_gains": values,
        "uncertainty": "依据近28天完整周的净进步估算；学习时间、课程难度和证据不足都会影响结果。",
    }
    if remaining == 0:
        return GoalForecast(status="achieved", reason="当前知识范围已初步达标，仍需复习与验证", **common)
    if len(values) < 2 or any(v <= 0 for v in values):
        return GoalForecast(
            status="insufficient_data",
            reason="需要至少两个完整周且每周都有正向净进步，当前无法可靠预测",
            **common,
        )
    early = as_of.date() + timedelta(weeks=math.ceil(remaining / max(values)))
    late = as_of.date() + timedelta(weeks=math.ceil(remaining / min(values)))
    reason = "按已观察到的每周速度给出范围，不表示保证完成"
    if target_date and late.isoformat() > target_date:
        reason += "；估计范围可能超过目标日期，可检查排期"
    return GoalForecast(
        status="estimated", earliest=early.isoformat(), latest=late.isoformat(), reason=reason, **common
    )


def count_mastered(snapshot, at):
    values = compute_states(
        list(snapshot.concepts),
        [e for e in snapshot.events if datetime.fromisoformat(e["occurred_at"]) < at],
        snapshot.bkt_parameters,
    )
    scope = effective_scope(snapshot.concepts, snapshot.intent)["included_ids"]
    return sum(values[k]["status"] == "mastered" for k in scope)


def forecast_snapshot(snapshot, period):
    tz, _ = zone(period.timezone)
    gains = []
    first = min(
        (datetime.fromisoformat(e["occurred_at"]) for e in snapshot.events if e["type"] in ASSESSMENTS),
        default=snapshot.now,
    )
    cutoff = min(period.end, snapshot.now)
    # Window selection is independent of whether the requested report is a preview.
    local = cutoff.astimezone(tz)
    latest_closed = local.date() - timedelta(days=local.weekday() + 7)
    window_start = make_period(local.date() - timedelta(days=28), 1, tz, None).start
    for offset in (3, 2, 1, 0):
        start = latest_closed - timedelta(weeks=offset)
        week = make_period(start, 7, tz, None)
        if window_start <= week.start and week.end <= cutoff and first <= week.start:
            gains.append(count_mastered(snapshot, week.end) - count_mastered(snapshot, week.start))
    scope = effective_scope(snapshot.concepts, snapshot.intent)["included_ids"]
    remaining = len(scope) - count_mastered(snapshot, min(period.end, snapshot.now))
    return forecast_goal(
        remaining, gains, min(period.end, snapshot.now).astimezone(tz), snapshot.intent.get("target_date")
    )


def summarize_week(snapshot, period, weekly_progress=()):
    end = min(period.end, snapshot.now)
    recent = [e for e in snapshot.events if period.start <= datetime.fromisoformat(e["occurred_at"]) < end]
    answers = [e for e in recent if e["type"] in ASSESSMENTS]
    reliable = [
        e
        for e in answers
        if e.get("confidence") == "high"
        and isinstance(e.get("is_correct"), bool)
        and not e.get("evaluator", "").startswith("llm_rubric:")
        and len(e.get("concept_ids", [])) == 1
    ]
    reviews = [e for e in reliable if e["type"] == "review_submitted"]
    # Denominator: tasks started this week, plus tasks carried in and completed
    # this week. This records each actual completion in its completion week.
    done = [
        t
        for t in snapshot.tasks
        if t.get("completed_at") and period.start <= datetime.fromisoformat(t["completed_at"]) < end
    ]
    starts = [
        t
        for t in snapshot.tasks
        if t.get("started_at") and period.start <= datetime.fromisoformat(t["started_at"]) < end
    ]
    carried_done = [
        t for t in done if not t.get("started_at") or datetime.fromisoformat(t["started_at"]) < period.start
    ]
    names = {c["key"]: c["name"] for c in snapshot.concepts}
    evidence = sum(len(observations_for(c["key"], recent).observations) for c in snapshot.concepts)
    return WeeklySummaryResponse(
        id="preview",
        study_space_id=snapshot.space_id,
        week_start=period.key,
        timezone=period.timezone,
        window_start=period.start.isoformat(),
        window_end=end.isoformat(),
        as_of=snapshot.now.isoformat(),
        fingerprint=snapshot.fingerprint,
        preview=True,
        intent_version=snapshot.intent["version"],
        due_reviews=sum(m["status"] == "due" for m in snapshot.memory.values()),
        answers=len(answers),
        independent=sum(e.get("assistance_level") == "none" for e in answers),
        assisted=sum(e.get("assistance_level") != "none" for e in answers),
        uncertain=len(answers) - len(reliable),
        before_mastered=count_mastered(snapshot, period.start),
        after_mastered=count_mastered(snapshot, end),
        evidence_count=evidence,
        error_concepts=sorted(
            {names[k] for e in reliable if e["is_correct"] is False for k in e["concept_ids"] if k in names}
        ),
        skipped_tasks=sum(
            t["status"] == "skipped"
            and bool(t.get("disposed_at"))
            and period.start <= datetime.fromisoformat(t["disposed_at"]) < end
            for t in snapshot.tasks
        ),
        review_retention=fraction(
            sum(e["is_correct"] and e.get("assistance_level") == "none" for e in reviews), len(reviews)
        ),
        task_completion=fraction(len(done), len(starts) + len(carried_done)),
        forecast=forecast_snapshot(snapshot, period),
        notice="完成率统计本周开始的任务，以及之前开始、本周完成的任务。掌握估计使用默认参数，尚未针对个人校准；目标日期根据学习记录推算，数据不足时暂不预测。",
    )


def summary_view(row):
    return WeeklySummaryResponse.model_validate(row.data)


def publish_week(session_factory, user_id, space_id, period, now, *, claim=None):
    with session_factory.begin() as db:
        _, space = lock_space(db, user_id, space_id)
        if claim:
            guard_claim(db, claim, now)
        row = db.scalar(
            select(WeeklySummary).where(
                WeeklySummary.space_id == space.id, WeeklySummary.week_start == period.key
            )
        )
        if row:
            return summary_view(row)
        snapshot = read_snapshot(db, space, now)
        report = summarize_week(snapshot, period)
        row = WeeklySummary(
            user_id=user_id, space_id=space_id, week_start=period.key, timezone=period.timezone
        )
        db.add(row)
        db.flush()
        report = report.model_copy(update={"id": row.id, "preview": False})
        row.data = report.model_dump()
        put_message(
            db, space, f"weekly:{period.key}", "weekly", row.id, f"{period.key}这一周的学习总结已生成。", now
        )
        return report
