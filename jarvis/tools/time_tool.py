from __future__ import annotations

from datetime import datetime, timezone

from jarvis.utils.time_utils import utc_now_iso


def _spoken_time_12h(now: datetime) -> str:
    hour_24 = now.hour
    minute = now.minute
    meridiem = "am" if hour_24 < 12 else "pm"
    hour_12 = hour_24 % 12 or 12
    if minute == 0:
        return f"{hour_12} {meridiem}"
    return f"{hour_12}:{minute:02d} {meridiem}"


def _ordinal(day: int) -> str:
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _spoken_date(now: datetime) -> str:
    weekday = now.strftime("%A")
    month = now.strftime("%B")
    return f"{weekday} the {_ordinal(now.day)} of {month}"


def local_now() -> dict[str, str]:
    now = datetime.now().astimezone()
    return {
        "iso": now.isoformat(),
        "local_time": now.strftime("%H:%M"),
        "spoken_time": _spoken_time_12h(now),
        "spoken_day": now.strftime("%A"),
        "spoken_date": _spoken_date(now),
        "local_date": now.strftime("%Y-%m-%d"),
        "timezone": now.tzname() or "local",
    }
