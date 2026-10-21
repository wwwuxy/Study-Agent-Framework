from app.db.models import AnalysisDailyUsage
from app.providers.base import ProviderError
from app.schemas.analyses import AnalysisUsageResponse


def reserve_usage(db, user_id, utc_date, run_id, tokens, limits):
    row = db.get(AnalysisDailyUsage, (user_id, utc_date))
    if row is None:
        row = AnalysisDailyUsage(user_id=user_id, utc_date=utc_date)
        db.add(row)
        db.flush()
    if (
        row.calls >= limits.m4_analysis_daily_call_limit
        or row.occupied_tokens + tokens > limits.m4_analysis_daily_token_limit
    ):
        raise ProviderError(
            "analysis_quota_exceeded",
            "今日 AI 分析额度已用完，可继续学习、复习和查看统计；额度重置后可再次分析",
            429,
        )
    row.calls += 1
    row.occupied_tokens += tokens
    row.unknown_calls += 1


def settle_usage(db, run, usage, now):
    if run.data.get("settled"):
        return
    known = (
        usage
        and usage.get("usage_reported") is True
        and all(type(usage.get(k)) is int and usage[k] >= 0 for k in ("prompt_tokens", "completion_tokens"))
    )
    row = db.get(AnalysisDailyUsage, (run.user_id, run.budget_date))
    if known:
        actual = usage["prompt_tokens"] + usage["completion_tokens"]
        row.occupied_tokens += actual - run.reserved_tokens
        row.actual_tokens += actual
        row.unknown_calls -= 1
        run.usage_tokens = actual
    run.data = {**run.data, "settled": True, "usage_status": "reported" if known else "unknown"}


def usage_view(db, user_id, now, limits):
    key = now.date().isoformat()
    row = db.get(AnalysisDailyUsage, (user_id, key))
    return AnalysisUsageResponse(
        utc_date=key,
        calls=row.calls if row else 0,
        call_limit=limits.m4_analysis_daily_call_limit,
        occupied_tokens=row.occupied_tokens if row else 0,
        actual_tokens=row.actual_tokens if row else 0,
        token_limit=limits.m4_analysis_daily_token_limit,
        unknown_calls=row.unknown_calls if row else 0,
        notice="仅统计手动发起的 AI 学习分析，同一账号下的学习空间共享每日额度，按 UTC 日期重置（北京时间每日 08:00）。未返回实际用量的请求暂按预留额度计入。",
    )
