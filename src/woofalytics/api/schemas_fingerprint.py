"""Pydantic schemas for fingerprint API requests and responses.

These schemas define the structure of all fingerprint-related API data,
providing automatic validation and documentation.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DogProfileSchema(BaseModel):
    """Dog profile for API responses."""

    id: str = Field(description="Unique identifier for the dog")
    name: str = Field(description="Name of the dog")
    notes: str = Field(default="", description="Optional notes about the dog")
    created_at: datetime = Field(description="When the profile was created")
    updated_at: datetime = Field(description="When the profile was last updated")
    sample_count: int = Field(default=0, description="Number of bark samples used to build this profile")
    first_seen: datetime | None = Field(default=None, description="First time this dog was detected")
    last_seen: datetime | None = Field(default=None, description="Most recent detection of this dog")
    total_barks: int = Field(default=0, description="Total number of barks attributed to this dog")
    avg_duration_ms: float | None = Field(default=None, description="Average bark duration in milliseconds")
    avg_pitch_hz: float | None = Field(default=None, description="Average bark pitch in Hz")

    model_config = {"from_attributes": True}


class DogProfileCreateSchema(BaseModel):
    """Request to create a new dog profile."""

    name: str = Field(default="", description="Name for the new dog")
    notes: str = Field(default="", description="Optional notes about the dog")


class DogProfileUpdateSchema(BaseModel):
    """Request to update an existing dog profile."""

    name: str | None = Field(default=None, description="New name for the dog")
    notes: str | None = Field(default=None, description="New notes for the dog")


class BarkFingerprintSchema(BaseModel):
    """Bark fingerprint for API responses."""

    id: str = Field(description="Unique identifier for the fingerprint")
    timestamp: datetime = Field(description="When the bark was detected")
    dog_id: str | None = Field(default=None, description="ID of the dog this bark is attributed to")
    dog_name: str | None = Field(default=None, description="Name of the dog (if attributed)")
    match_confidence: float | None = Field(default=None, description="Confidence of the dog identification (0-1)")
    cluster_id: str | None = Field(default=None, description="ID of the cluster this bark belongs to (if untagged)")
    evidence_filename: str | None = Field(default=None, description="Filename of the evidence recording")
    detection_probability: float = Field(default=0.0, description="Bark detection probability")
    doa_degrees: int | None = Field(default=None, description="Direction of arrival in degrees")
    duration_ms: float | None = Field(default=None, description="Duration of the bark in milliseconds")
    pitch_hz: float | None = Field(default=None, description="Pitch of the bark in Hz")
    spectral_centroid_hz: float | None = Field(default=None, description="Spectral centroid in Hz")

    model_config = {"from_attributes": True}


class FingerprintMatchSchema(BaseModel):
    """Result of matching a bark against known dog profiles."""

    dog_id: str = Field(description="ID of the matched dog")
    dog_name: str = Field(description="Name of the matched dog")
    confidence: float = Field(ge=0.0, le=1.0, description="Match confidence (0-1)")
    sample_count: int = Field(description="Number of samples used to build the dog's profile")


class FingerprintStatsSchema(BaseModel):
    """Statistics about the fingerprint database."""

    dogs: int = Field(description="Total number of dog profiles")
    fingerprints: int = Field(description="Total number of bark fingerprints")
    untagged: int = Field(description="Number of fingerprints not yet tagged to a dog")
    clusters: int = Field(description="Number of auto-detected clusters")


class TagBarkRequestSchema(BaseModel):
    """Request to tag a bark fingerprint to a dog."""

    dog_id: str = Field(description="ID of the dog to tag this bark to")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence of the tagging (default: 1.0 for manual tags)",
    )


class BulkTagRequestSchema(BaseModel):
    """Request to tag multiple bark fingerprints to a dog."""

    bark_ids: list[str] = Field(description="List of bark fingerprint IDs to tag")
    dog_id: str = Field(description="ID of the dog to tag these barks to")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence of the tagging (default: 1.0 for manual tags)",
    )


class CorrectBarkRequestSchema(BaseModel):
    """Request to correct a misidentified bark."""

    new_dog_id: str = Field(description="ID of the correct dog for this bark")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence of the correction (default: 1.0 for manual corrections)",
    )


class BulkTagResultSchema(BaseModel):
    """Result of a bulk tag operation."""

    tagged_count: int = Field(description="Number of barks successfully tagged")
    failed_count: int = Field(description="Number of barks that failed to tag")
    failed_ids: list[str] = Field(default_factory=list, description="IDs of barks that failed to tag")


class UntaggedBarksListSchema(BaseModel):
    """List of untagged bark fingerprints."""

    count: int = Field(description="Number of untagged barks returned")
    total_untagged: int = Field(description="Total number of untagged barks in the database")
    barks: list[BarkFingerprintSchema] = Field(description="List of untagged bark fingerprints")


class DogBarksListSchema(BaseModel):
    """List of bark fingerprints for a specific dog."""

    dog_id: str = Field(description="ID of the dog")
    dog_name: str = Field(description="Name of the dog")
    count: int = Field(description="Number of barks returned")
    total_barks: int = Field(description="Total number of barks for this dog")
    barks: list[BarkFingerprintSchema] = Field(description="List of bark fingerprints")
