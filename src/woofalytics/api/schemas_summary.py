"""Pydantic schemas for bark summary reports API.

These schemas define the structure for daily, weekly, and monthly
bark statistics summaries.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PeriodSummarySchema(BaseModel):
    """Base schema for period-based bark statistics."""

    total_barks: int
    total_events: int
    total_duration_seconds: float
    avg_confidence: float
    peak_hour: int | None = None  # 0-23, hour with most barks


class DailySummarySchema(PeriodSummarySchema):
    """Daily bark summary with hourly breakdown."""

    date: str  # YYYY-MM-DD format
    hourly_breakdown: dict[int, int]  # hour (0-23) -> bark count


class WeeklySummarySchema(PeriodSummarySchema):
    """Weekly bark summary with daily breakdown."""

    week_start: datetime
    week_end: datetime
    daily_breakdown: dict[str, int]  # date (YYYY-MM-DD) -> bark count


class MonthlySummarySchema(PeriodSummarySchema):
    """Monthly bark summary with daily breakdown."""

    month: str  # YYYY-MM format
    daily_breakdown: dict[str, int]  # date (YYYY-MM-DD) -> bark count


class AISummarySchema(BaseModel):
    """AI-generated natural language summary of bark data."""

    summary: str  # Natural language summary from LLM
    model: str  # Model used for generation
    generation_time_ms: int  # Time taken to generate
    data_period: str  # Period summarized (e.g., "2026-01-01 to 2026-01-07")
