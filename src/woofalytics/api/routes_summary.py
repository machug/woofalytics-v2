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
    DogBreakdownItem,
    MonthlySummarySchema,
    RangeSummarySchema,
    WeeklySummarySchema,
)
from woofalytics.evidence.metadata import EvidenceMetadata
from woofalytics.evidence.storage import EvidenceStorage
from woofalytics.fingerprint.storage import FingerprintStore

router = APIRouter(prefix="/summary", tags=["summary"])

# Ollama configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

# Prompty configuration - load template once
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_weekly_summary_prompty: prompty.Prompty | None = None


# --- Dependency Injection ---


def get_evidence(request: Request) -> EvidenceStorage:
    """Get evidence storage from app state."""
    return request.app.state.evidence


def get_fingerprint_store(request: Request) -> FingerprintStore:
    """Get fingerprint store from app state."""
    return request.app.state.fingerprint_store


# --- Helper Functions ---


def _get_per_dog_bark_counts(
    store: FingerprintStore,
    start: datetime,
    end: datetime,
) -> list[DogBreakdownItem]:
    """Query per-dog bark counts for confirmed dogs in a date range."""
    with store._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT dp.id, dp.name, COUNT(bf.id) as bark_count
            FROM bark_fingerprints bf
            JOIN dog_profiles dp ON bf.dog_id = dp.id
            WHERE bf.timestamp >= ? AND bf.timestamp < ?
              AND dp.confirmed = 1
            GROUP BY dp.id, dp.name
            ORDER BY bark_count DESC
            """,
            (start.isoformat(), end.isoformat()),
        )
        return [
            DogBreakdownItem(
                dog_id=row["id"],
                dog_name=row["name"],
                bark_count=row["bark_count"],
            )
            for row in cursor.fetchall()
        ]


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
        local_time = entry.timestamp_utc.astimezone(LOCAL_TZ)
        hourly[local_time.hour] += entry.detection.bark_count_in_clip

    peak_hour = max(hourly, key=hourly.get) if hourly else None
    return total_barks, total_events, total_duration, avg_confidence, peak_hour, dict(hourly)


def _calculate_daily_breakdown(entries: list[EvidenceMetadata]) -> dict[str, int]:
    """Calculate daily bark counts from entries."""
    daily: dict[str, int] = defaultdict(int)
    for entry in entries:
        local_time = entry.timestamp_utc.astimezone(LOCAL_TZ)
        daily[local_time.strftime("%Y-%m-%d")] += entry.detection.bark_count_in_clip
    return dict(daily)


def _filter_by_date_range(
    entries: list[EvidenceMetadata],
    start: datetime,
    end: datetime,
) -> list[EvidenceMetadata]:
    """Filter entries to those within the date range."""
    return [e for e in entries if start <= e.timestamp_utc < end]


def _parse_date(date_str: str | None, default: datetime) -> datetime:
    """Parse a date string or return default."""
    if date_str is None:
        return default
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format: {date_str}. Use YYYY-MM-DD.",
        )


def _parse_date_range(start_date: str, end_date: str) -> tuple[datetime, datetime]:
    """Parse and validate a date range.

    Returns:
        Tuple of (range_start, range_end_exclusive)
    """
    try:
        range_start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid start_date format: {start_date}. Use YYYY-MM-DD.",
        )

    try:
        range_end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid end_date format: {end_date}. Use YYYY-MM-DD.",
        )

    if range_start > range_end:
        raise HTTPException(
            status_code=400,
            detail="start_date must be before or equal to end_date.",
        )

    return range_start, range_end + timedelta(days=1)


def _get_week_boundaries(date: datetime) -> tuple[datetime, datetime]:
    """Get Monday-Sunday boundaries for the week containing the date."""
    monday = date - timedelta(days=date.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    return monday, monday + timedelta(days=7)


def _get_month_boundaries(year: int, month: int) -> tuple[datetime, datetime]:
    """Get first and last+1 day boundaries for a month."""
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, end


# --- Summary Endpoints ---


@router.get("/daily", response_model=DailySummarySchema)
async def daily_summary(
    evidence: EvidenceStorage = Depends(get_evidence),
    date: str | None = Query(
        default=None,
        description="Date in YYYY-MM-DD format. Defaults to today.",
    ),
) -> DailySummarySchema:
    """Get daily bark summary with hourly breakdown."""
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    target_date = _parse_date(date, today)

    day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    entries = _filter_by_date_range(evidence._index.entries, day_start, day_start + timedelta(days=1))

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
    """Get weekly bark summary with daily breakdown."""
    target_date = _parse_date(date, datetime.now(timezone.utc))
    week_start, week_end = _get_week_boundaries(target_date)

    entries = _filter_by_date_range(evidence._index.entries, week_start, week_end)
    total_barks, total_events, total_duration, avg_confidence, peak_hour, _ = (
        _calculate_period_stats(entries)
    )

    return WeeklySummarySchema(
        week_start=week_start,
        week_end=week_end - timedelta(seconds=1),
        total_barks=total_barks,
        total_events=total_events,
        total_duration_seconds=total_duration,
        avg_confidence=round(avg_confidence, 4),
        peak_hour=peak_hour,
        daily_breakdown=_calculate_daily_breakdown(entries),
    )


@router.get("/monthly", response_model=MonthlySummarySchema)
async def monthly_summary(
    evidence: EvidenceStorage = Depends(get_evidence),
    month: str | None = Query(
        default=None,
        description="Month in YYYY-MM format. Defaults to current month.",
    ),
) -> MonthlySummarySchema:
    """Get monthly bark summary with daily breakdown."""
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

    return MonthlySummarySchema(
        month=month_str,
        total_barks=total_barks,
        total_events=total_events,
        total_duration_seconds=total_duration,
        avg_confidence=round(avg_confidence, 4),
        peak_hour=peak_hour,
        daily_breakdown=_calculate_daily_breakdown(entries),
    )


@router.get("/range", response_model=RangeSummarySchema)
async def range_summary(
    request: Request,
    evidence: EvidenceStorage = Depends(get_evidence),
    start_date: str = Query(description="Start date in YYYY-MM-DD format."),
    end_date: str = Query(description="End date in YYYY-MM-DD format (inclusive)."),
) -> RangeSummarySchema:
    """Get bark summary for a custom date range."""
    range_start, range_end_exclusive = _parse_date_range(start_date, end_date)
    entries = _filter_by_date_range(evidence._index.entries, range_start, range_end_exclusive)

    total_barks, total_events, total_duration, avg_confidence, peak_hour, hourly = (
        _calculate_period_stats(entries)
    )

    fingerprint_store = get_fingerprint_store(request)
    dog_breakdown = _get_per_dog_bark_counts(fingerprint_store, range_start, range_end_exclusive)

    return RangeSummarySchema(
        start_date=start_date,
        end_date=end_date,
        total_barks=total_barks,
        total_events=total_events,
        total_duration_seconds=total_duration,
        avg_confidence=round(avg_confidence, 4),
        peak_hour=peak_hour,
        daily_breakdown=_calculate_daily_breakdown(entries),
        hourly_breakdown=hourly,
        dog_breakdown=dog_breakdown,
    )


# --- AI Summary Helpers ---


def _get_weekly_summary_prompty() -> prompty.Prompty:
    """Lazily load the weekly summary prompty template."""
    global _weekly_summary_prompty
    if _weekly_summary_prompty is None:
        prompty_path = _PROMPTS_DIR / "weekly_summary.prompty"
        _weekly_summary_prompty = prompty.load(str(prompty_path))
    return _weekly_summary_prompty


def _format_duration(total_seconds: float) -> str:
    """Format duration in seconds to human-readable string."""
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    if hours > 0:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    return f"{minutes}m"


def _format_llm_prompt(
    start_display: str,
    end_display: str,
    total_barks: int,
    total_events: int,
    total_duration_seconds: float,
    avg_confidence: float,
    peak_hour: int | None,
    daily_breakdown: dict[str, int],
    per_dog_counts: list[DogBreakdownItem],
) -> str:
    """Format bark data as a prompt for the LLM."""
    peak_hour_str = f"{peak_hour}:00-{peak_hour + 1}:00" if peak_hour is not None else "N/A"

    # Format daily breakdown
    daily_lines = []
    for day, count in sorted(daily_breakdown.items()):
        try:
            day_name = datetime.strptime(day, "%Y-%m-%d").strftime("%A, %B %d")
        except ValueError:
            day_name = day
        daily_lines.append(f"- {day_name}: {count} barks")
    daily_text = "\n".join(daily_lines) if daily_lines else "No data recorded"

    # Format per-dog breakdown
    if per_dog_counts:
        dog_lines = ["| Dog Name | Barks |", "|----------|-------|"]
        for dog in per_dog_counts:
            dog_lines.append(f"| {dog.dog_name} | {dog.bark_count} |")
        per_dog_text = "\n".join(dog_lines)
    else:
        per_dog_text = "No individual dogs identified yet."

    # Render template
    prompty_obj = _get_weekly_summary_prompty()
    renderer = Jinja2Renderer(prompty=prompty_obj)

    return renderer.invoke({
        "week_start": start_display,
        "week_end": end_display,
        "total_barks": total_barks,
        "total_events": total_events,
        "total_hours": _format_duration(total_duration_seconds),
        "daily_breakdown": daily_text,
        "per_dog_breakdown": per_dog_text,
        "peak_hour_str": peak_hour_str,
        "avg_confidence": f"{avg_confidence:.0%}",
    })


async def _call_ollama(prompt: str) -> tuple[str, int]:
    """Call Ollama and return (response_text, generation_time_ms)."""
    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
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

    generation_time_ms = int((time.time() - start_time) * 1000)
    return result.get("response", "").strip(), generation_time_ms


# --- AI Summary Endpoints ---


@router.get("/weekly/ai", response_model=AISummarySchema)
async def weekly_ai_summary(
    request: Request,
    evidence: EvidenceStorage = Depends(get_evidence),
    date: str | None = Query(
        default=None,
        description="Any date within the week (YYYY-MM-DD). Defaults to current week.",
    ),
) -> AISummarySchema:
    """Get AI-generated summary of weekly bark data."""
    target_date = _parse_date(date, datetime.now(timezone.utc))
    week_start, week_end = _get_week_boundaries(target_date)

    entries = _filter_by_date_range(evidence._index.entries, week_start, week_end)
    total_barks, total_events, total_duration, avg_confidence, peak_hour, _ = (
        _calculate_period_stats(entries)
    )

    fingerprint_store = get_fingerprint_store(request)
    per_dog_counts = _get_per_dog_bark_counts(fingerprint_store, week_start, week_end)

    prompt = _format_llm_prompt(
        start_display=week_start.strftime("%B %d"),
        end_display=(week_end - timedelta(seconds=1)).strftime("%B %d, %Y"),
        total_barks=total_barks,
        total_events=total_events,
        total_duration_seconds=total_duration,
        avg_confidence=avg_confidence,
        peak_hour=peak_hour,
        daily_breakdown=_calculate_daily_breakdown(entries),
        per_dog_counts=per_dog_counts,
    )

    summary_text, generation_time_ms = await _call_ollama(prompt)

    return AISummarySchema(
        summary=summary_text,
        model=OLLAMA_MODEL,
        generation_time_ms=generation_time_ms,
        data_period=f"{week_start.strftime('%Y-%m-%d')} to {(week_end - timedelta(seconds=1)).strftime('%Y-%m-%d')}",
    )


@router.get("/ai", response_model=AISummarySchema)
async def range_ai_summary(
    request: Request,
    evidence: EvidenceStorage = Depends(get_evidence),
    start_date: str = Query(description="Start date in YYYY-MM-DD format."),
    end_date: str = Query(description="End date in YYYY-MM-DD format (inclusive)."),
) -> AISummarySchema:
    """Get AI-generated summary for a custom date range."""
    range_start, range_end_exclusive = _parse_date_range(start_date, end_date)

    entries = _filter_by_date_range(evidence._index.entries, range_start, range_end_exclusive)
    total_barks, total_events, total_duration, avg_confidence, peak_hour, _ = (
        _calculate_period_stats(entries)
    )

    fingerprint_store = get_fingerprint_store(request)
    per_dog_counts = _get_per_dog_bark_counts(fingerprint_store, range_start, range_end_exclusive)

    # Parse dates for display
    try:
        start_display = datetime.strptime(start_date, "%Y-%m-%d").strftime("%B %d")
        end_display = datetime.strptime(end_date, "%Y-%m-%d").strftime("%B %d, %Y")
    except ValueError:
        start_display, end_display = start_date, end_date

    prompt = _format_llm_prompt(
        start_display=start_display,
        end_display=end_display,
        total_barks=total_barks,
        total_events=total_events,
        total_duration_seconds=total_duration,
        avg_confidence=avg_confidence,
        peak_hour=peak_hour,
        daily_breakdown=_calculate_daily_breakdown(entries),
        per_dog_counts=per_dog_counts,
    )

    summary_text, generation_time_ms = await _call_ollama(prompt)

    return AISummarySchema(
        summary=summary_text,
        model=OLLAMA_MODEL,
        generation_time_ms=generation_time_ms,
        data_period=f"{start_date} to {end_date}",
    )
