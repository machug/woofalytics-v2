"""Data export API routes.

Provides endpoints for exporting bark event data in CSV and JSON formats
for external analysis, council complaints, and legal documentation.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from woofalytics.api.schemas_export import (
    ExportEntrySchema,
    ExportResponseSchema,
    ExportStatsSchema,
)
from woofalytics.evidence.metadata import EvidenceMetadata
from woofalytics.evidence.storage import EvidenceStorage

router = APIRouter(prefix="/export", tags=["export"])


def get_evidence(request: Request) -> EvidenceStorage:
    """Get evidence storage from app state."""
    return request.app.state.evidence


def _filter_entries(
    entries: list[EvidenceMetadata],
    start_date: datetime | None,
    end_date: datetime | None,
    min_confidence: float,
) -> list[EvidenceMetadata]:
    """Filter entries by date range and confidence threshold."""
    # Ensure dates are timezone-aware for comparison with timestamp_utc
    if start_date and start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date and end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)

    filtered = []
    for entry in entries:
        # Date range filter
        if start_date and entry.timestamp_utc < start_date:
            continue
        if end_date and entry.timestamp_utc > end_date:
            continue
        # Confidence filter (peak probability)
        if entry.detection.peak_probability < min_confidence:
            continue
        filtered.append(entry)
    return filtered


def _entry_to_schema(entry: EvidenceMetadata) -> ExportEntrySchema:
    """Convert EvidenceMetadata to export schema."""
    return ExportEntrySchema(
        timestamp_utc=entry.timestamp_utc,
        timestamp_local=entry.timestamp_local,
        duration_seconds=entry.duration_seconds,
        trigger_probability=entry.detection.trigger_probability,
        peak_probability=entry.detection.peak_probability,
        bark_count=entry.detection.bark_count_in_clip,
        doa_degrees=entry.detection.doa_degrees,
        filename=entry.filename,
    )


@router.get("/json", response_model=ExportResponseSchema)
async def export_json(
    evidence: Annotated[EvidenceStorage, Depends(get_evidence)],
    start_date: datetime | None = Query(
        default=None,
        description="Filter events on or after this UTC datetime",
    ),
    end_date: datetime | None = Query(
        default=None,
        description="Filter events on or before this UTC datetime",
    ),
    min_confidence: float = Query(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum confidence threshold (0.0-1.0)",
    ),
) -> ExportResponseSchema:
    """Export bark events as JSON.

    Returns filtered bark event data as a JSON array.
    Useful for external analysis tools and integrations.
    """
    entries = _filter_entries(
        evidence._index.entries,
        start_date,
        end_date,
        min_confidence,
    )

    return ExportResponseSchema(
        count=len(entries),
        exported_at=datetime.now(timezone.utc),
        filters={
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "min_confidence": min_confidence,
        },
        entries=[_entry_to_schema(e) for e in entries],
    )


@router.get("/csv")
async def export_csv(
    evidence: Annotated[EvidenceStorage, Depends(get_evidence)],
    start_date: datetime | None = Query(
        default=None,
        description="Filter events on or after this UTC datetime",
    ),
    end_date: datetime | None = Query(
        default=None,
        description="Filter events on or before this UTC datetime",
    ),
    min_confidence: float = Query(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum confidence threshold (0.0-1.0)",
    ),
) -> StreamingResponse:
    """Export bark events as CSV.

    Returns filtered bark event data as a downloadable CSV file.
    Useful for spreadsheet analysis and council complaints.
    """
    entries = _filter_entries(
        evidence._index.entries,
        start_date,
        end_date,
        min_confidence,
    )

    def generate_csv():
        output = io.StringIO()
        writer = csv.writer(output)

        # Header row
        writer.writerow([
            "timestamp_utc",
            "timestamp_local",
            "duration_seconds",
            "trigger_probability",
            "peak_probability",
            "bark_count",
            "doa_degrees",
            "filename",
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        # Data rows
        for entry in entries:
            writer.writerow([
                entry.timestamp_utc.isoformat(),
                entry.timestamp_local.isoformat(),
                f"{entry.duration_seconds:.2f}",
                f"{entry.detection.trigger_probability:.4f}",
                f"{entry.detection.peak_probability:.4f}",
                entry.detection.bark_count_in_clip,
                entry.detection.doa_degrees or "",
                entry.filename,
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    # Generate filename with current date
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"woofalytics-export-{date_str}.csv"

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/stats", response_model=ExportStatsSchema)
async def export_stats(
    evidence: Annotated[EvidenceStorage, Depends(get_evidence)],
    start_date: datetime | None = Query(
        default=None,
        description="Filter events on or after this UTC datetime",
    ),
    end_date: datetime | None = Query(
        default=None,
        description="Filter events on or before this UTC datetime",
    ),
    min_confidence: float = Query(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum confidence threshold (0.0-1.0)",
    ),
) -> ExportStatsSchema:
    """Get statistics about exportable data.

    Returns counts and summaries without downloading the full dataset.
    Useful for checking data availability before export.
    """
    entries = _filter_entries(
        evidence._index.entries,
        start_date,
        end_date,
        min_confidence,
    )

    total_barks = sum(e.detection.bark_count_in_clip for e in entries)
    total_duration = sum(e.duration_seconds for e in entries)

    # Get actual date range from filtered data
    date_start = None
    date_end = None
    if entries:
        timestamps = [e.timestamp_utc for e in entries]
        date_start = min(timestamps)
        date_end = max(timestamps)

    return ExportStatsSchema(
        total_entries=len(entries),
        total_barks=total_barks,
        total_duration_seconds=total_duration,
        date_range_start=date_start,
        date_range_end=date_end,
    )
