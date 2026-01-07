"""Bark summary report API routes.

Provides endpoints for daily, weekly, and monthly bark statistics
with time-based breakdowns for analysis and reporting.
"""

from __future__ import annotations

import os
import time
from calendar import monthrange
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import prompty
from prompty.renderers import Jinja2Renderer

# Get system local timezone
LOCAL_TZ = datetime.now().astimezone().tzinfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from woofalytics.api.schemas_summary import (
    AISummarySchema,
    DailySummarySchema,
    MonthlySummarySchema,
    WeeklySummarySchema,
)
from woofalytics.evidence.metadata import EvidenceMetadata
from woofalytics.evidence.storage import EvidenceStorage
from woofalytics.fingerprint.storage import FingerprintStore

router = APIRouter(prefix="/summary", tags=["summary"])


def get_evidence(request: Request) -> EvidenceStorage:
    """Get evidence storage from app state."""
    return request.app.state.evidence


def get_fingerprint_store(request: Request) -> FingerprintStore:
    """Get fingerprint store from app state."""
    return request.app.state.fingerprint_store


def _get_per_dog_bark_counts(
    store: FingerprintStore,
    start: datetime,
    end: datetime,
) -> list[tuple[str, int]]:
    """Query per-dog bark counts for confirmed dogs in a date range.

    Returns:
        List of (dog_name, bark_count) tuples sorted by count descending.
    """
    with store._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT dp.name, COUNT(bf.id) as bark_count
            FROM bark_fingerprints bf
            JOIN dog_profiles dp ON bf.dog_id = dp.id
            WHERE bf.timestamp >= ? AND bf.timestamp < ?
              AND dp.confirmed = 1
            GROUP BY dp.id, dp.name
            ORDER BY bark_count DESC
            """,
            (start.isoformat(), end.isoformat()),
        )
        return [(row["name"], row["bark_count"]) for row in cursor.fetchall()]


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

    # Calculate hourly breakdown (in local time)
    hourly: dict[int, int] = defaultdict(int)
    for entry in entries:
        # Convert UTC to local time for hourly display
        local_time = entry.timestamp_utc.astimezone(LOCAL_TZ)
        hour = local_time.hour
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

    # Calculate daily breakdown (in local time)
    daily: dict[str, int] = defaultdict(int)
    for entry in entries:
        local_time = entry.timestamp_utc.astimezone(LOCAL_TZ)
        day_str = local_time.strftime("%Y-%m-%d")
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

    # Calculate daily breakdown (in local time)
    daily: dict[str, int] = defaultdict(int)
    for entry in entries:
        local_time = entry.timestamp_utc.astimezone(LOCAL_TZ)
        day_str = local_time.strftime("%Y-%m-%d")
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


# Ollama configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

# Prompty configuration - load template once
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_weekly_summary_prompty: prompty.Prompty | None = None


def _get_weekly_summary_prompty() -> prompty.Prompty:
    """Lazily load the weekly summary prompty template."""
    global _weekly_summary_prompty
    if _weekly_summary_prompty is None:
        prompty_path = _PROMPTS_DIR / "weekly_summary.prompty"
        _weekly_summary_prompty = prompty.load(str(prompty_path))
    return _weekly_summary_prompty


def _format_weekly_prompt(
    data: WeeklySummarySchema,
    per_dog_counts: list[tuple[str, int]] | None = None,
) -> str:
    """Format weekly data as a prompt for the LLM using prompty template."""
    # Format peak hour
    peak_hour_str = f"{data.peak_hour}:00-{data.peak_hour + 1}:00" if data.peak_hour else "N/A"

    # Calculate total hours of disturbance (duration in seconds -> hours and minutes)
    total_seconds = data.total_duration_seconds
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    if hours > 0 and minutes > 0:
        total_hours_str = f"{hours} hour{'s' if hours != 1 else ''} {minutes} minutes"
    elif hours > 0:
        total_hours_str = f"{hours} hour{'s' if hours != 1 else ''}"
    else:
        total_hours_str = f"{minutes} minutes"

    # Format daily breakdown as readable text
    daily_lines = []
    for day, count in sorted(data.daily_breakdown.items()):
        try:
            day_date = datetime.strptime(day, "%Y-%m-%d")
            day_name = day_date.strftime("%A, %B %d")
        except ValueError:
            day_name = day
        daily_lines.append(f"- {day_name}: {count} barks")
    daily_breakdown_text = "\n".join(daily_lines) if daily_lines else "No data recorded"

    # Format per-dog breakdown as a table
    if per_dog_counts:
        dog_lines = ["| Dog Name | Barks This Week |", "|----------|-----------------|"]
        for dog_name, bark_count in per_dog_counts:
            dog_lines.append(f"| {dog_name} | {bark_count} |")
        per_dog_text = "\n".join(dog_lines)
    else:
        per_dog_text = "No individual dogs identified yet."

    # Load and render the prompty template
    prompty_obj = _get_weekly_summary_prompty()
    renderer = Jinja2Renderer(prompty=prompty_obj)

    rendered = renderer.invoke({
        "week_start": data.week_start.strftime("%B %d"),
        "week_end": data.week_end.strftime("%B %d, %Y"),
        "total_barks": data.total_barks,
        "total_events": data.total_events,
        "total_hours": total_hours_str,
        "daily_breakdown": daily_breakdown_text,
        "per_dog_breakdown": per_dog_text,
        "peak_hour_str": peak_hour_str,
        "avg_confidence": f"{data.avg_confidence:.0%}",
    })

    return rendered


@router.get("/weekly/ai", response_model=AISummarySchema)
async def weekly_ai_summary(
    request: Request,
    evidence: EvidenceStorage = Depends(get_evidence),
    date: str | None = Query(
        default=None,
        description="Any date within the week (YYYY-MM-DD). Defaults to current week.",
    ),
) -> AISummarySchema:
    """Get AI-generated natural language summary of weekly bark data.

    Uses a local LLM (Ollama) to generate a formal council complaint report
    about the week's bark activity patterns. Requires Ollama to be running locally.
    """
    # Get the weekly data first
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
        local_time = entry.timestamp_utc.astimezone(LOCAL_TZ)
        day_str = local_time.strftime("%Y-%m-%d")
        daily[day_str] += entry.detection.bark_count_in_clip

    weekly_data = WeeklySummarySchema(
        week_start=week_start,
        week_end=week_end - timedelta(seconds=1),
        total_barks=total_barks,
        total_events=total_events,
        total_duration_seconds=total_duration,
        avg_confidence=round(avg_confidence, 4),
        peak_hour=peak_hour,
        daily_breakdown=dict(daily),
    )

    # Get per-dog bark counts from fingerprint store
    fingerprint_store = get_fingerprint_store(request)
    per_dog_counts = _get_per_dog_bark_counts(fingerprint_store, week_start, week_end)

    # Generate the prompt
    prompt = _format_weekly_prompt(weekly_data, per_dog_counts)

    # Call Ollama
    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            response.raise_for_status()
            result = response.json()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Ollama service not available. Is it running?",
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Ollama error: {e.response.text}",
        )

    generation_time = int((time.time() - start_time) * 1000)

    return AISummarySchema(
        summary=result.get("response", "").strip(),
        model=OLLAMA_MODEL,
        generation_time_ms=generation_time,
        data_period=f"{week_start.strftime('%Y-%m-%d')} to {(week_end - timedelta(seconds=1)).strftime('%Y-%m-%d')}",
    )
