"""Data models for audio fingerprinting and dog identification.

These models define the structure for storing dog profiles, bark fingerprints,
and match results. Designed for SQLite storage with numpy array serialization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import numpy as np


def _generate_id() -> str:
    """Generate a unique ID for new records."""
    return uuid4().hex[:12]


@dataclass
class DogProfile:
    """Profile for an identified dog.

    Represents a recognized dog with its name, cumulative fingerprint,
    and statistics about bark history.

    A dog must be "confirmed" before auto-tagging is enabled. This requires
    manually tagging a minimum number of barks to build a reliable fingerprint.
    """

    id: str = field(default_factory=_generate_id)
    name: str = ""
    notes: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Confirmation status - dog must be confirmed before auto-tagging
    confirmed: bool = False
    confirmed_at: datetime | None = None

    # Minimum samples required before auto-tagging (user-configurable per dog)
    min_samples_for_auto_tag: int = 5

    # Cumulative embedding: weighted average of all fingerprints for this dog
    # Shape: (512,) - CLAP embedding dimension
    embedding: np.ndarray | None = None

    # Number of bark samples used to build this profile
    sample_count: int = 0

    # Statistics
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    total_barks: int = 0

    # Acoustic characteristics (computed from samples)
    avg_duration_ms: float | None = None
    avg_pitch_hz: float | None = None

    def can_auto_tag(self) -> bool:
        """Check if this dog is eligible for auto-tagging.

        Returns True only if:
        1. Dog is confirmed
        2. Has enough samples (>= min_samples_for_auto_tag)
        """
        return self.confirmed and self.sample_count >= self.min_samples_for_auto_tag

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "confirmed": self.confirmed,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "min_samples_for_auto_tag": self.min_samples_for_auto_tag,
            "sample_count": self.sample_count,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "total_barks": self.total_barks,
            "avg_duration_ms": self.avg_duration_ms,
            "avg_pitch_hz": self.avg_pitch_hz,
            # Embedding stored separately as binary
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], embedding: np.ndarray | None = None) -> DogProfile:
        """Create from dictionary with optional embedding."""
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            notes=data.get("notes", ""),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            confirmed=data.get("confirmed", False),
            confirmed_at=datetime.fromisoformat(data["confirmed_at"]) if data.get("confirmed_at") else None,
            min_samples_for_auto_tag=data.get("min_samples_for_auto_tag", 5),
            embedding=embedding,
            sample_count=data.get("sample_count", 0),
            first_seen=datetime.fromisoformat(data["first_seen"]) if data.get("first_seen") else None,
            last_seen=datetime.fromisoformat(data["last_seen"]) if data.get("last_seen") else None,
            total_barks=data.get("total_barks", 0),
            avg_duration_ms=data.get("avg_duration_ms"),
            avg_pitch_hz=data.get("avg_pitch_hz"),
        )

    def update_embedding(self, new_embedding: np.ndarray, weight: float = 1.0) -> None:
        """Update cumulative embedding with a new sample.

        Uses weighted running average to incrementally learn the dog's
        bark signature as more samples are collected.

        Args:
            new_embedding: New 512-dim CLAP embedding.
            weight: Weight for the new sample (higher = more influence).
        """
        if self.embedding is None:
            self.embedding = new_embedding.copy()
            self.sample_count = 1
        else:
            # Weighted running average
            total_weight = self.sample_count + weight
            self.embedding = (
                self.embedding * self.sample_count + new_embedding * weight
            ) / total_weight
            self.sample_count += 1

        # Normalize to unit vector for cosine similarity
        norm = np.linalg.norm(self.embedding)
        if norm > 0:
            self.embedding = self.embedding / norm

        self.updated_at = datetime.now(timezone.utc)


@dataclass
class BarkFingerprint:
    """Fingerprint for an individual bark event.

    Stores the CLAP embedding and acoustic features for a single bark,
    linked to a dog profile (if identified) or cluster (if untagged).
    """

    id: str = field(default_factory=_generate_id)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # CLAP embedding (512-dim)
    embedding: np.ndarray | None = None

    # Link to dog profile (None if untagged)
    dog_id: str | None = None

    # Match confidence when dog was identified (0-1)
    match_confidence: float | None = None

    # Link to cluster (for untagged barks)
    cluster_id: str | None = None

    # Link to evidence file (if recorded)
    evidence_filename: str | None = None

    # Rejection status (if marked as false positive)
    # Values: None (not rejected), "speech", "wind", "bird", "other", or custom text
    rejection_reason: str | None = None

    # Confirmation status (None = unreviewed, True = confirmed bark, False = dismissed)
    confirmed: bool | None = None
    confirmed_at: datetime | None = None

    # Detection metadata
    detection_probability: float = 0.0
    doa_degrees: int | None = None

    # Acoustic features (for secondary matching)
    duration_ms: float | None = None
    pitch_hz: float | None = None
    spectral_centroid_hz: float | None = None
    mfcc_mean: np.ndarray | None = None  # (13,) mean MFCCs

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "dog_id": self.dog_id,
            "match_confidence": self.match_confidence,
            "cluster_id": self.cluster_id,
            "evidence_filename": self.evidence_filename,
            "rejection_reason": self.rejection_reason,
            "confirmed": self.confirmed,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "detection_probability": self.detection_probability,
            "doa_degrees": self.doa_degrees,
            "duration_ms": self.duration_ms,
            "pitch_hz": self.pitch_hz,
            "spectral_centroid_hz": self.spectral_centroid_hz,
            # Embeddings stored separately as binary
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        embedding: np.ndarray | None = None,
        mfcc_mean: np.ndarray | None = None,
    ) -> BarkFingerprint:
        """Create from dictionary with optional embeddings."""
        return cls(
            id=data["id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            embedding=embedding,
            dog_id=data.get("dog_id"),
            match_confidence=data.get("match_confidence"),
            cluster_id=data.get("cluster_id"),
            evidence_filename=data.get("evidence_filename"),
            rejection_reason=data.get("rejection_reason"),
            confirmed=data.get("confirmed"),
            confirmed_at=datetime.fromisoformat(data["confirmed_at"]) if data.get("confirmed_at") else None,
            detection_probability=data.get("detection_probability", 0.0),
            doa_degrees=data.get("doa_degrees"),
            duration_ms=data.get("duration_ms"),
            pitch_hz=data.get("pitch_hz"),
            spectral_centroid_hz=data.get("spectral_centroid_hz"),
            mfcc_mean=mfcc_mean,
        )


@dataclass
class FingerprintMatch:
    """Result of matching a bark against known dog profiles."""

    dog_id: str
    dog_name: str
    confidence: float  # 0-1, cosine similarity
    sample_count: int  # How many samples built this profile

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "dog_id": self.dog_id,
            "dog_name": self.dog_name,
            "confidence": round(self.confidence, 4),
            "sample_count": self.sample_count,
        }


