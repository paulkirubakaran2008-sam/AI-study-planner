from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def safe_zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "Asia/Kolkata")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Asia/Kolkata")


def local_now(tz_name: str | None) -> datetime:
    """Naive datetime in the student's own timezone."""
    return datetime.now(timezone.utc).astimezone(safe_zone(tz_name)).replace(tzinfo=None)


def hhmm(minute: int) -> str:
    minute = max(0, min(24 * 60, int(minute)))
    return f"{minute // 60:02d}:{minute % 60:02d}"


def parse_hhmm(value: str) -> int:
    h, m = value.split(":")
    return int(h) * 60 + int(m)


def ceil5(x: int) -> int:
    return (x + 4) // 5 * 5


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())
