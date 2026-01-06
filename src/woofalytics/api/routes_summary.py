"""Bark summary report API routes.

Provides endpoints for daily, weekly, and monthly bark statistics
with time-based breakdowns for analysis and reporting.
"""

from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from woofalytics.api.schemas_summary import (
    DailySummarySchema,
    MonthlySummarySchema,
    WeeklySummarySchema,
)
from woofalytics.evidence.metadata import EvidenceMetadata
from woofalytics.evidence.storage import EvidenceStorage

router = APIRouter(prefix="/summary", tags=["summary"])


def get_evidence(request: Request) -> EvidenceStorage:
    """Get evidence storage from app state."""
    return request.app.state.evidence


def _calculate_period_stats(
    entries: list[EvidenceMetadata],
) -> tuple[int, int, float, float, int | None, dict[int, int]]:
    """Calculate statistics for a list of entries.

    Returns:
        Tuple of (total_barks, total_events, total_duration, avg_confidence,
                  peak_hour, hourly_breakdown)
    """
    if not entries:
        return 0, 0, 0.0, 0.0, None, {}

    total_barks = sum(e.detection.bark_count_in_clip for e in entries)
    total_events = len(entries)
    total_duration = sum(e.duration_seconds for e in entries)
    avg_confidence = sum(e.detection.peak_probability for e in entries) / total_events

    # Calculate hourly breakdown
    hourly: dict[int, int] = defaultdict(int)
    for entry in entries:
        hour = entry.timestamp_utc.hour
        hourly[hour] += entry.detection.bark_count_in_clip

    # Find peak hour
    peak_hour = max(hourly, key=hourly.get) if hourly else None

    return total_barks, total_events, total_duration, avg_confidence, peak_hour, dict(hourly)


def _filter_by_date_range(
    entries: list[EvidenceMetadata],
    start: datetime,
    end: datetime,
) -> list[EvidenceMetadata]:
    """Filter entries to those within the date range."""
    return [
        e for e in entries
        if start <= e.timestamp_utc < end
    ]


def _parse_date(date_str: str | None, default: datetime) -> datetime:
    """Parse a date string or return default."""
    if date_str is None:
        return default
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d")
        return parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format: {date_str}. Use YYYY-MM-DD.",
        )


def _get_week_boundaries(date: datetime) -> tuple[datetime, datetime]:
    """Get Monday-Sunday boundaries for the week containing the date."""
    # Find Monday of the week (weekday() returns 0 for Monday)
    monday = date - timedelta(days=date.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    sunday_end = monday + timedelta(days=7)
    return monday, sunday_end


def _get_month_boundaries(year: int, month: int) -> tuple[datetime, datetime]:
    """Get first and last+1 day boundaries for a month."""
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    _, last_day = monthrange(year, month)
    # End is first day of next month
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, end


@router.get("/daily", response_model=DailySummarySchema)
async def daily_summary(
    evidence: EvidenceStorage = Depends(get_evidence),
    date: str | None = Query(
        default=None,
        description="Date in YYYY-MM-DD format. Defaults to today.",
    ),
) -> DailySummarySchema:
    """Get daily bark summary with hourly breakdown.

    Returns total barks, events, duration, average confidence,
    peak hour, and barks per hour for the specified date.
    """
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    target_date = _parse_date(date, today)

    # Filter entries for this day
    day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    entries = _filter_by_date_range(evidence._index.entries, day_start, day_end)

    total_barks, total_events, total_duration, avg_confidence, peak_hour, hourly = (
        _calculate_period_stats(entries)
    )

    return DailySummarySchema(
        date=target_date.strftime("%Y-%m-%d"),
        total_barks=total_barks,
        total_events=total_events,
        total_duration_seconds=total_duration,
        avg_confidence=round(avg_confidence, 4),
        peak_hour=peak_hour,
        hourly_breakdown=hourly,
    )


@router.get("/weekly", response_model=WeeklySummarySchema)
async def weekly_summary(
    evidence: EvidenceStorage = Depends(get_evidence),
    date: str | None = Query(
        default=None,
        description="Any date within the week (YYYY-MM-DD). Defaults to current week.",
    ),
) -> WeeklySummarySchema:
    """Get weekly bark summary with daily breakdown.

    Returns total barks, events, duration, average confidence,
    peak hour, and barks per day for the week containing the specified date.
    """
    today = datetime.now(timezone.utc)
    target_date = _parse_date(date, today)

    week_start, week_end = _get_week_boundaries(target_date)

    entries = _filter_by_date_range(evidence._index.entries, week_start, week_end)

    total_barks, total_events, total_duration, avg_confidence, peak_hour, _ = (
        _calculate_period_stats(entries)
    )

    # Calculate daily breakdown
    daily: dict[str, int] = defaultdict(int)
    for entry in entries:
        day_str = entry.timestamp_utc.strftime("%Y-%m-%d")
        daily[day_str] += entry.detection.bark_count_in_clip

    return WeeklySummarySchema(
        week_start=week_start,
        week_end=week_end - timedelta(seconds=1),  # End of Sunday
        total_barks=total_barks,
        total_events=total_events,
        total_duration_seconds=total_duration,
        avg_confidence=round(avg_confidence, 4),
        peak_hour=peak_hour,
        daily_breakdown=dict(daily),
    )


@router.get("/monthly", response_model=MonthlySummarySchema)
async def monthly_summary(
    evidence: EvidenceStorage = Depends(get_evidence),
    month: str | None = Query(
        default=None,
        description="Month in YYYY-MM format. Defaults to current month.",
    ),
) -> MonthlySummarySchema:
    """Get monthly bark summary with daily breakdown.

    Returns total barks, events, duration, average confidence,
    peak hour, and barks per day for the specified month.
    """
    today = datetime.now(timezone.utc)

    if month is None:
        year, mon = today.year, today.month
        month_str = today.strftime("%Y-%m")
    else:
        try:
            parsed = datetime.strptime(month, "%Y-%m")
            year, mon = parsed.year, parsed.month
            month_str = month
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid month format: {month}. Use YYYY-MM.",
            )

    month_start, month_end = _get_month_boundaries(year, mon)

    entries = _filter_by_date_range(evidence._index.entries, month_start, month_end)

    total_barks, total_events, total_duration, avg_confidence, peak_hour, _ = (
        _calculate_period_stats(entries)
    )

    # Calculate daily breakdown
    daily: dict[str, int] = defaultdict(int)
    for entry in entries:
        day_str = entry.timestamp_utc.strftime("%Y-%m-%d")
        daily[day_str] += entry.detection.bark_count_in_clip

    return MonthlySummarySchema(
        month=month_str,
        total_barks=total_barks,
        total_events=total_events,
        total_duration_seconds=total_duration,
        avg_confidence=round(avg_confidence, 4),
        peak_hour=peak_hour,
        daily_breakdown=dict(daily),
    )
