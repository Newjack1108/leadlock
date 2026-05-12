from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import HTTPException

VALID_PRESET_PERIODS = ("all", "week", "month", "quarter", "year")


@dataclass(frozen=True)
class ResolvedDateRange:
    period: str
    start: datetime
    end: datetime
    is_custom: bool = False


def normalize_period(period: Optional[str], default: str = "all") -> str:
    normalized = (period or "").strip().lower()
    if normalized in VALID_PRESET_PERIODS:
        return normalized
    return default


def get_date_range_for_period(period: str) -> tuple[datetime, datetime]:
    normalized_period = normalize_period(period)
    now = datetime.utcnow()
    end = now

    if normalized_period == "week":
        start_of_week = now - timedelta(days=now.weekday())
        start = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    elif normalized_period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif normalized_period == "quarter":
        quarter_start_month = ((now.month - 1) // 3) * 3 + 1
        start = now.replace(month=quarter_start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif normalized_period == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start = datetime(1970, 1, 1)

    return start, end


def resolve_date_range(
    *,
    period: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    default_period: str = "all",
) -> ResolvedDateRange:
    has_custom_dates = bool(start_date or end_date)

    if has_custom_dates:
        normalized_period = (period or "").strip().lower()
        if normalized_period and normalized_period not in ("custom",):
            raise HTTPException(status_code=400, detail="Use either period or start_date/end_date, not both")
        if not start_date or not end_date:
            raise HTTPException(status_code=400, detail="Both start_date and end_date are required for a custom range")
        try:
            start_day = date.fromisoformat(start_date)
            end_day = date.fromisoformat(end_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="start_date and end_date must use YYYY-MM-DD format") from exc
        if end_day < start_day:
            raise HTTPException(status_code=400, detail="end_date must be on or after start_date")

        return ResolvedDateRange(
            period="custom",
            start=datetime.combine(start_day, time.min),
            end=datetime.combine(end_day, time.max),
            is_custom=True,
        )

    normalized_period = normalize_period(period, default=default_period)
    start, end = get_date_range_for_period(normalized_period)
    return ResolvedDateRange(
        period=normalized_period,
        start=start,
        end=end,
        is_custom=False,
    )
