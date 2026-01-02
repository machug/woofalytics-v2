"""Metadata models for evidence recordings.

This module defines the structured metadata format for bark evidence,
designed to be useful for council complaints and legal documentation.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class DetectionInfo:
    """Detection metrics for the bark event."""

    trigger_probability: float
    peak_probability: float
    bark_count_in_clip: int
    doa_bartlett: int | None = None
    doa_capon: int | None = None
    doa_mem: int | None = None

    @property
    def doa_degrees(self) -> int | None:
        """Get primary DOA estimate (Bartlett method)."""
        return self.doa_bartlett

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "trigger_probability": round(self.trigger_probability, 4),
            "peak_probability": round(self.peak_probability, 4),
            "bark_count_in_clip": self.bark_count_in_clip,
            "doa_bartlett": self.doa_bartlett,
            "doa_capon": self.doa_capon,
            "doa_mem": self.doa_mem,
        }


@dataclass
class DeviceInfo:
    """Device information for provenance tracking."""

    hostname: str = field(default_factory=socket.gethostname)
    microphone: str = "Unknown"

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for JSON serialization."""
        return {
            "hostname": self.hostname,
            "microphone": self.microphone,
        }


@dataclass
class EvidenceMetadata:
    """Complete metadata for an evidence recording.

    This structured format is designed for:
    - Council complaints requiring timestamped evidence
    - Legal documentation with device provenance
    - Analysis and pattern recognition over time
    """

    filename: str
    timestamp_utc: datetime
    timestamp_local: datetime
    duration_seconds: float
    sample_rate: int
    channels: int
    detection: DetectionInfo
    device: DeviceInfo

    @classmethod
    def create(
        cls,
        filename: str,
        duration_seconds: float,
        sample_rate: int,
        channels: int,
        trigger_probability: float,
        peak_probability: float,
        bark_count: int,
        microphone_name: str,
        doa_bartlett: int | None = None,
        doa_capon: int | None = None,
        doa_mem: int | None = None,
    ) -> EvidenceMetadata:
        """Create metadata with current timestamp.

        Args:
            filename: Name of the WAV file.
            duration_seconds: Duration of the recording.
            sample_rate: Audio sample rate in Hz.
            channels: Number of audio channels.
            trigger_probability: Probability that triggered recording.
            peak_probability: Maximum probability in the clip.
            bark_count: Number of bark detections in the clip.
            microphone_name: Name of the recording device.
            doa_bartlett: Direction of arrival (Bartlett method).
            doa_capon: Direction of arrival (Capon method).
            doa_mem: Direction of arrival (MEM method).

        Returns:
            Configured EvidenceMetadata instance.
        """
        now_utc = datetime.now(timezone.utc)
        now_local = datetime.now().astimezone()

        return cls(
            filename=filename,
            timestamp_utc=now_utc,
            timestamp_local=now_local,
            duration_seconds=duration_seconds,
            sample_rate=sample_rate,
            channels=channels,
            detection=DetectionInfo(
                trigger_probability=trigger_probability,
                peak_probability=peak_probability,
                bark_count_in_clip=bark_count,
                doa_bartlett=doa_bartlett,
                doa_capon=doa_capon,
                doa_mem=doa_mem,
            ),
            device=DeviceInfo(
                microphone=microphone_name,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "filename": self.filename,
            "timestamp_utc": self.timestamp_utc.isoformat(),
            "timestamp_local": self.timestamp_local.isoformat(),
            "duration_seconds": round(self.duration_seconds, 2),
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "detection": self.detection.to_dict(),
            "device": self.device.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceMetadata:
        """Create from dictionary (JSON deserialization).

        Args:
            data: Dictionary containing metadata fields.

        Returns:
            EvidenceMetadata instance.
        """
        return cls(
            filename=data["filename"],
            timestamp_utc=datetime.fromisoformat(data["timestamp_utc"]),
            timestamp_local=datetime.fromisoformat(data["timestamp_local"]),
            duration_seconds=data["duration_seconds"],
            sample_rate=data["sample_rate"],
            channels=data["channels"],
            detection=DetectionInfo(
                trigger_probability=data["detection"]["trigger_probability"],
                peak_probability=data["detection"]["peak_probability"],
                bark_count_in_clip=data["detection"]["bark_count_in_clip"],
                doa_bartlett=data["detection"].get("doa_bartlett"),
                doa_capon=data["detection"].get("doa_capon"),
                doa_mem=data["detection"].get("doa_mem"),
            ),
            device=DeviceInfo(
                hostname=data["device"]["hostname"],
                microphone=data["device"]["microphone"],
            ),
        )


@dataclass
class EvidenceIndex:
    """Index of all evidence files for quick lookup.

    Maintained as a JSON file for efficient querying without
    scanning all individual metadata files.
    """

    entries: list[EvidenceMetadata] = field(default_factory=list)
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add(self, metadata: EvidenceMetadata) -> None:
        """Add a new entry to the index."""
        self.entries.append(metadata)
        self.last_updated = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "last_updated": self.last_updated.isoformat(),
            "count": len(self.entries),
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceIndex:
        """Create from dictionary (JSON deserialization)."""
        return cls(
            entries=[EvidenceMetadata.from_dict(e) for e in data.get("entries", [])],
            last_updated=datetime.fromisoformat(data.get("last_updated", datetime.now(timezone.utc).isoformat())),
        )

    def get_by_date_range(
        self,
        start: datetime,
        end: datetime,
    ) -> list[EvidenceMetadata]:
        """Get entries within a date range."""
        return [
            e for e in self.entries
            if start <= e.timestamp_utc <= end
        ]

    def get_recent(self, count: int = 10) -> list[EvidenceMetadata]:
        """Get most recent entries."""
        sorted_entries = sorted(
            self.entries,
            key=lambda e: e.timestamp_utc,
            reverse=True,
        )
        return sorted_entries[:count]

    @property
    def total_duration_seconds(self) -> float:
        """Get total duration of all recordings."""
        return sum(e.duration_seconds for e in self.entries)

    @property
    def total_bark_count(self) -> int:
        """Get total bark count across all recordings."""
        return sum(e.detection.bark_count_in_clip for e in self.entries)
