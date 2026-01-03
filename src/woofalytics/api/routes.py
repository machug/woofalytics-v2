"""REST API routes for Woofalytics.

This module provides endpoints for:
- Health and status checks
- Bark detection status and history
- Evidence file listing and retrieval
- Configuration viewing
- Dog profile management and bark tagging (via fingerprint router)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response

from woofalytics.api.routes_fingerprint import router as fingerprint_router
from woofalytics.api.schemas import (
    BarkEventSchema,
    ConfigurationSchema,
    DetectorStatusSchema,
    EvidenceFileSchema,
    EvidenceListSchema,
    EvidenceStatsSchema,
    HealthSchema,
    PurgeEvidenceRequestSchema,
    PurgeFingerprintsRequestSchema,
    PurgeResultSchema,
    RecentEventsSchema,
)
from woofalytics.config import Settings
from woofalytics.detection.model import BarkDetector, BarkEvent
from woofalytics.detection.doa import angle_to_direction
from woofalytics.evidence.storage import EvidenceStorage
from woofalytics.fingerprint.storage import FingerprintStore
from woofalytics.observability.metrics import generate_latest, get_metrics

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["api"])

# Include fingerprint routes for dog profile and bark tagging management
router.include_router(fingerprint_router)


# Dependency injection
def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_detector(request: Request) -> BarkDetector:
    return request.app.state.detector


def get_evidence(request: Request) -> EvidenceStorage:
    return request.app.state.evidence


def get_fingerprint_store(request: Request) -> FingerprintStore:
    """Get fingerprint store from app state.

    The store is lazily initialized on first access.
    """
    if not hasattr(request.app.state, "fingerprint_store"):
        settings = request.app.state.settings
        db_path = Path(settings.evidence.directory) / "fingerprints.db"
        request.app.state.fingerprint_store = FingerprintStore(db_path)
        logger.info("fingerprint_store_initialized", db_path=str(db_path))
    return request.app.state.fingerprint_store


def bark_event_to_schema(event: BarkEvent) -> BarkEventSchema:
    """Convert BarkEvent to API schema."""
    return BarkEventSchema(
        timestamp=event.timestamp,
        probability=event.probability,
        is_barking=event.is_barking,
        doa_bartlett=event.doa_bartlett,
        doa_capon=event.doa_capon,
        doa_mem=event.doa_mem,
    )


@router.get("/health", response_model=HealthSchema)
async def health_check(
    detector: Annotated[BarkDetector, Depends(get_detector)],
    evidence: Annotated[EvidenceStorage, Depends(get_evidence)],
) -> HealthSchema:
    """Health check endpoint.

    Returns overall system health including uptime,
    bark count, and evidence file count.
    """
    return HealthSchema(
        status="healthy" if detector.is_running else "degraded",
        uptime_seconds=detector.uptime_seconds,
        total_barks_detected=detector.total_barks_detected,
        evidence_files_count=evidence.total_recordings,
    )


@router.get("/status", response_model=DetectorStatusSchema)
async def get_status(
    detector: Annotated[BarkDetector, Depends(get_detector)],
) -> DetectorStatusSchema:
    """Get current detector status.

    Returns running state, uptime, bark count, and last event.
    """
    status = detector.get_status()
    last_event = detector.get_last_event()

    return DetectorStatusSchema(
        running=status["running"],
        uptime_seconds=status["uptime_seconds"],
        total_barks=status["total_barks"],
        last_event=bark_event_to_schema(last_event) if last_event else None,
        microphone=status["microphone"],
    )


@router.get("/bark", response_model=BarkEventSchema | None)
async def get_last_bark(
    detector: Annotated[BarkDetector, Depends(get_detector)],
) -> BarkEventSchema | None:
    """Get the most recent bark detection event.

    This is useful for simple polling-based UIs.
    For real-time updates, use the WebSocket endpoint.
    """
    event = detector.get_last_event()
    if event:
        return bark_event_to_schema(event)
    return None


@router.get("/bark/probability")
async def get_bark_probability(
    detector: Annotated[BarkDetector, Depends(get_detector)],
) -> dict[str, float | None]:
    """Get just the current bark probability.

    Lightweight endpoint for simple integrations.
    Returns {"probability": 0.95} or {"probability": null} if no data.
    """
    event = detector.get_last_event()
    return {"probability": event.probability if event else None}


@router.get("/bark/recent", response_model=RecentEventsSchema)
async def get_recent_barks(
    detector: Annotated[BarkDetector, Depends(get_detector)],
    count: Annotated[int, Query(ge=1, le=100)] = 10,
) -> RecentEventsSchema:
    """Get recent bark detection events.

    Args:
        count: Number of events to return (1-100, default 10).

    Returns list of recent events for display or analysis.
    """
    events = detector.get_recent_events(count)
    return RecentEventsSchema(
        count=len(events),
        events=[bark_event_to_schema(e) for e in events],
    )


@router.get("/evidence", response_model=EvidenceListSchema)
async def list_evidence(
    evidence: Annotated[EvidenceStorage, Depends(get_evidence)],
    count: Annotated[int, Query(ge=1, le=100)] = 20,
) -> EvidenceListSchema:
    """List recent evidence recordings.

    Args:
        count: Number of recordings to return (1-100, default 20).

    Returns metadata for recent evidence files.
    """
    recordings = evidence.get_recent_evidence(count)

    files = [
        EvidenceFileSchema(
            filename=r.filename,
            timestamp_utc=r.timestamp_utc,
            timestamp_local=r.timestamp_local,
            duration_seconds=r.duration_seconds,
            sample_rate=r.sample_rate,
            channels=r.channels,
            trigger_probability=r.detection.trigger_probability,
            peak_probability=r.detection.peak_probability,
            bark_count_in_clip=r.detection.bark_count_in_clip,
            doa_degrees=r.detection.doa_degrees,
        )
        for r in recordings
    ]

    return EvidenceListSchema(count=len(files), evidence=files)


@router.get("/evidence/stats", response_model=EvidenceStatsSchema)
async def get_evidence_stats(
    evidence: Annotated[EvidenceStorage, Depends(get_evidence)],
) -> EvidenceStatsSchema:
    """Get evidence storage statistics.

    Returns totals for recordings, duration, and bark count.
    """
    stats = evidence.get_stats()
    # Redact filesystem path for security (consistent with /api/config)
    stats.pop("storage_directory", None)
    return EvidenceStatsSchema(**stats)


@router.get("/evidence/{filename}")
async def download_evidence(
    filename: str,
    settings: Annotated[Settings, Depends(get_settings)],
    format: Annotated[str | None, Query(description="Audio format: 'opus' for compressed")] = None,
) -> FileResponse:
    """Download an evidence file (WAV or JSON metadata).

    Args:
        filename: Name of the file to download.
        format: Optional format conversion. Use 'opus' for compressed web playback.

    Returns the file for download or streaming.
    """
    import asyncio
    import subprocess

    # Security: reject any path components in filename FIRST
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    # Only allow expected file types
    if not (filename.endswith(".wav") or filename.endswith(".json")):
        raise HTTPException(status_code=400, detail="Invalid file type")

    # Build path and validate it's within evidence directory BEFORE checking existence
    evidence_dir = settings.evidence.directory.resolve()
    file_path = (evidence_dir / filename).resolve()

    # Verify path is within evidence directory (defense in depth)
    if not file_path.is_relative_to(evidence_dir):
        raise HTTPException(status_code=403, detail="Access denied")

    # Now safe to check existence
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Evidence file not found")

    # Handle Opus transcoding for web playback
    if format == "opus" and filename.endswith(".wav"):
        cache_dir = evidence_dir / ".cache"
        cache_dir.mkdir(exist_ok=True)
        opus_filename = filename.replace(".wav", ".opus")
        opus_path = cache_dir / opus_filename

        # Transcode if not cached
        if not opus_path.exists():
            try:
                # FFmpeg: convert to Opus at 64kbps (excellent quality for voice/barks)
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", str(file_path),
                    "-c:a", "libopus", "-b:a", "64k",
                    "-vbr", "on", "-compression_level", "10",
                    str(opus_path),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                await proc.wait()
                if proc.returncode != 0:
                    raise HTTPException(status_code=500, detail="Audio transcoding failed")
            except FileNotFoundError:
                raise HTTPException(status_code=500, detail="FFmpeg not available")

        return FileResponse(
            path=opus_path,
            filename=opus_filename,
            media_type="audio/opus",
        )

    media_type = "audio/wav" if filename.endswith(".wav") else "application/json"

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=media_type,
    )


@router.get("/evidence/date/{date}")
async def get_evidence_by_date(
    date: str,
    evidence: Annotated[EvidenceStorage, Depends(get_evidence)],
) -> EvidenceListSchema:
    """Get evidence recordings for a specific date.

    Args:
        date: Date in YYYY-MM-DD format.

    Returns evidence files from the specified date.
    """
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD.",
        )

    start = target_date
    end = target_date + timedelta(days=1)

    recordings = evidence.get_evidence_by_date(start, end)

    files = [
        EvidenceFileSchema(
            filename=r.filename,
            timestamp_utc=r.timestamp_utc,
            timestamp_local=r.timestamp_local,
            duration_seconds=r.duration_seconds,
            sample_rate=r.sample_rate,
            channels=r.channels,
            trigger_probability=r.detection.trigger_probability,
            peak_probability=r.detection.peak_probability,
            bark_count_in_clip=r.detection.bark_count_in_clip,
            doa_degrees=r.detection.doa_degrees,
        )
        for r in recordings
    ]

    return EvidenceListSchema(count=len(files), evidence=files)


@router.get("/config", response_model=ConfigurationSchema)
async def get_configuration(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ConfigurationSchema:
    """Get current configuration (sanitized).

    Returns configuration values without sensitive data
    like API keys, webhook secrets, or filesystem paths.
    """
    return ConfigurationSchema(
        audio={
            "device_name": settings.audio.device_name,
            "sample_rate": settings.audio.sample_rate,
            "channels": settings.audio.channels,
            "chunk_size": settings.audio.chunk_size,
            "volume_percent": settings.audio.volume_percent,
        },
        model={
            # Path redacted - only expose operational parameters
            "threshold": settings.model.threshold,
            "target_sample_rate": settings.model.target_sample_rate,
        },
        doa={
            "enabled": settings.doa.enabled,
            "element_spacing": settings.doa.element_spacing,
            "num_elements": settings.doa.num_elements,
            "angle_min": settings.doa.angle_min,
            "angle_max": settings.doa.angle_max,
            "method": settings.doa.method,
        },
        evidence={
            # Directory path redacted for security
            "past_context_seconds": settings.evidence.past_context_seconds,
            "future_context_seconds": settings.evidence.future_context_seconds,
            "include_metadata": settings.evidence.include_metadata,
        },
        server={
            # Host redacted - only expose port for client use
            "port": settings.server.port,
            "enable_websocket": settings.server.enable_websocket,
        },
        log_level=settings.log_level,
    )


@router.get("/direction")
async def get_current_direction(
    detector: Annotated[BarkDetector, Depends(get_detector)],
) -> dict:
    """Get current direction of arrival estimate.

    Returns the estimated direction using all three methods
    (Bartlett, Capon, MEM) and human-readable descriptions.
    """
    event = detector.get_last_event()

    if not event or event.doa_bartlett is None:
        return {
            "available": False,
            "message": "No DOA data available",
        }

    return {
        "available": True,
        "bartlett": {
            "angle": event.doa_bartlett,
            "direction": angle_to_direction(event.doa_bartlett),
        },
        "capon": {
            "angle": event.doa_capon,
            "direction": angle_to_direction(event.doa_capon) if event.doa_capon else None,
        },
        "mem": {
            "angle": event.doa_mem,
            "direction": angle_to_direction(event.doa_mem) if event.doa_mem else None,
        },
    }


@router.get("/metrics", tags=["observability"])
async def prometheus_metrics(
    detector: Annotated[BarkDetector, Depends(get_detector)],
) -> Response:
    """Prometheus metrics endpoint.

    Returns metrics in Prometheus text exposition format for scraping.
    Includes counters, histograms, and gauges for:
    - bark_detections_total: Total bark detections
    - inference_total: Total inference runs (by model type)
    - inference_latency_seconds: Inference latency histogram
    - vad_skipped_total: VAD-skipped inferences
    - detector_running: Detector running status
    - uptime_seconds: Detector uptime
    - total_barks: Current total barks gauge
    """
    # Update gauges with current detector state
    metrics = get_metrics()
    if metrics.is_initialized:
        metrics.set_running(detector.is_running)
        metrics.set_uptime(detector.uptime_seconds)
        metrics.set_total_barks(detector.total_barks_detected)

    # Generate Prometheus text format
    content = generate_latest()

    return Response(
        content=content,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


# --- Maintenance Endpoints ---


@router.delete(
    "/fingerprints/{fingerprint_id}",
    status_code=204,
    tags=["maintenance"],
    summary="Delete a fingerprint",
    description="Deletes a single fingerprint by ID.",
)
async def delete_fingerprint(
    fingerprint_id: str,
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> None:
    """Delete a single fingerprint."""
    deleted = store.delete_fingerprint(fingerprint_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Fingerprint not found")
    logger.info("fingerprint_deleted_via_api", fingerprint_id=fingerprint_id)


@router.post(
    "/maintenance/purge-fingerprints",
    response_model=PurgeResultSchema,
    tags=["maintenance"],
    summary="Purge fingerprints",
    description="Bulk delete fingerprints based on criteria. Requires at least one filter "
    "(before date and/or untagged_only) to prevent accidental full purge.",
)
async def purge_fingerprints(
    data: PurgeFingerprintsRequestSchema,
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> PurgeResultSchema:
    """Purge fingerprints matching criteria."""
    if data.before is None and not data.untagged_only:
        raise HTTPException(
            status_code=400,
            detail="At least one filter required (before date or untagged_only=true)",
        )

    deleted_count = store.purge_fingerprints(
        before=data.before,
        untagged_only=data.untagged_only,
    )

    logger.info(
        "fingerprints_purged_via_api",
        deleted_count=deleted_count,
        before=data.before.isoformat() if data.before else None,
        untagged_only=data.untagged_only,
    )

    return PurgeResultSchema(
        deleted_count=deleted_count,
        resource_type="fingerprints",
    )


@router.post(
    "/maintenance/purge-evidence",
    response_model=PurgeResultSchema,
    tags=["maintenance"],
    summary="Purge evidence files",
    description="Bulk delete evidence files based on date criteria. Requires at least "
    "one filter (before and/or after) to prevent accidental full purge.",
)
async def purge_evidence(
    data: PurgeEvidenceRequestSchema,
    evidence: Annotated[EvidenceStorage, Depends(get_evidence)],
) -> PurgeResultSchema:
    """Purge evidence files matching criteria."""
    if data.before is None and data.after is None:
        raise HTTPException(
            status_code=400,
            detail="At least one filter required (before and/or after date)",
        )

    deleted_count = await evidence.purge_evidence(
        before=data.before,
        after=data.after,
    )

    logger.info(
        "evidence_purged_via_api",
        deleted_count=deleted_count,
        before=data.before.isoformat() if data.before else None,
        after=data.after.isoformat() if data.after else None,
    )

    return PurgeResultSchema(
        deleted_count=deleted_count,
        resource_type="evidence",
    )
