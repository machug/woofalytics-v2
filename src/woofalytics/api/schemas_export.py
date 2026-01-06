"""Pydantic schemas for data export API.

These schemas define the structure for export filtering
and response formats.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ExportEntrySchema(BaseModel):
    """A single exported bark event entry."""

    timestamp_utc: datetime
    timestamp_local: datetime
    duration_seconds: float
    trigger_probability: float
    peak_probability: float
    bark_count: int
    doa_degrees: int | None = None
    filename: str


class ExportResponseSchema(BaseModel):
    """JSON export response."""

    count: int
    exported_at: datetime
    filters: dict[str, str | float | None]
    entries: list[ExportEntrySchema]


class ExportStatsSchema(BaseModel):
    """Statistics about the exported data."""

    total_entries: int
    total_barks: int
    total_duration_seconds: float
    date_range_start: datetime | None = None
    date_range_end: datetime | None = None
