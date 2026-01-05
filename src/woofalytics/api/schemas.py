"""Pydantic schemas for API requests and responses.

These schemas define the structure of all API data,
providing automatic validation and documentation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from woofalytics import __version__


class BarkEventSchema(BaseModel):
    """A bark detection event."""

    timestamp: datetime
    probability: float = Field(ge=0.0, le=1.0)
    is_barking: bool
    doa_bartlett: int | None = None
    doa_capon: int | None = None
    doa_mem: int | None = None


class GateStatsSchema(BaseModel):
    """Statistics for a pipeline gate (VAD or YAMNet)."""

    passed: int
    skipped: int
    total: int
    skip_rate: float = Field(ge=0.0, le=1.0)


class DetectorStatusSchema(BaseModel):
    """Current detector status."""

    running: bool
    uptime_seconds: float
    total_barks: int
    last_event: BarkEventSchema | None = None
    microphone: str | None = None
    vad_stats: GateStatsSchema | None = None
    yamnet_stats: GateStatsSchema | None = None


class HealthSchema(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str = __version__
    uptime_seconds: float
    total_barks_detected: int
    evidence_files_count: int


class EvidenceFileSchema(BaseModel):
    """Evidence file metadata for API responses."""

    filename: str
    timestamp_utc: datetime
    timestamp_local: datetime
    duration_seconds: float
    sample_rate: int
    channels: int
    trigger_probability: float
    peak_probability: float
    bark_count_in_clip: int
    doa_degrees: int | None = None


class EvidenceStatsSchema(BaseModel):
    """Evidence storage statistics."""

    total_recordings: int
    total_duration_seconds: float
    total_barks_recorded: int


class EvidenceListSchema(BaseModel):
    """List of evidence files."""

    count: int
    evidence: list[EvidenceFileSchema]


class ConfigurationSchema(BaseModel):
    """Current configuration (sanitized, no secrets)."""

    audio: dict[str, Any]
    model: dict[str, Any]
    doa: dict[str, Any]
    evidence: dict[str, Any]
    server: dict[str, Any]
    log_level: str


class WebSocketMessageSchema(BaseModel):
    """WebSocket message format."""

    type: str
    data: dict[str, Any]


class RecentEventsSchema(BaseModel):
    """Recent bark detection events."""

    count: int
    events: list[BarkEventSchema]


class DirectionSchema(BaseModel):
    """Direction of arrival information."""

    angle_degrees: int | None
    direction: str  # "left", "front", "right", etc.
    method: str  # "bartlett", "capon", "mem"


# --- Maintenance Schemas ---


class PurgeFingerprintsRequestSchema(BaseModel):
    """Request to purge fingerprints."""

    before: datetime | None = Field(
        default=None,
        description="Delete fingerprints before this timestamp.",
    )
    untagged_only: bool = Field(
        default=False,
        description="Only delete untagged fingerprints.",
    )


class PurgeEvidenceRequestSchema(BaseModel):
    """Request to purge evidence files."""

    before: datetime | None = Field(
        default=None,
        description="Delete evidence files before this timestamp.",
    )
    after: datetime | None = Field(
        default=None,
        description="Delete evidence files after this timestamp.",
    )


class PurgeResultSchema(BaseModel):
    """Result of a purge operation."""

    deleted_count: int
    resource_type: str  # "fingerprints" or "evidence"
