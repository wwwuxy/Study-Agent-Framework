from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.activity.contracts import CalendarPeriod


def zone(timezone):
    try:
        return ZoneInfo(timezone), None
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return ZoneInfo("Asia/Shanghai"), "账号时区无效，当前使用 Asia/Shanghai"


def period(start, days, timezone, warning):
    beginning = datetime.combine(start, time.min, timezone)
    ending = datetime.combine(start + timedelta(days=days), time.min, timezone)
    return CalendarPeriod(
        start.isoformat(), str(timezone), beginning.astimezone(UTC), ending.astimezone(UTC), warning
    )


def local_day(now, timezone):
    tz, warning = zone(timezone)
    return period(now.astimezone(tz).date(), 1, tz, warning)


def previous_week(now, timezone):
    tz, warning = zone(timezone)
    day = now.astimezone(tz).date()
    return period(day - timedelta(days=day.weekday() + 7), 7, tz, warning)


def current_week(now, timezone):
    tz, warning = zone(timezone)
    day = now.astimezone(tz).date()
    return period(day - timedelta(days=day.weekday()), 7, tz, warning)
