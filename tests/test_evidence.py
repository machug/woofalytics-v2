"""Tests for evidence storage module."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from woofalytics.evidence.metadata import (
    DetectionInfo,
    DeviceInfo,
    EvidenceIndex,
    EvidenceMetadata,
)


class TestDetectionInfo:
    """Tests for DetectionInfo dataclass."""

    def test_creation(self):
        """Test detection info creation."""
        info = DetectionInfo(
            trigger_probability=0.88,
            peak_probability=0.95,
            bark_count_in_clip=5,
            doa_bartlett=90,
            doa_capon=88,
            doa_mem=92,
        )

        assert info.trigger_probability == 0.88
        assert info.peak_probability == 0.95
        assert info.bark_count_in_clip == 5
        assert info.doa_degrees == 90  # Property returns bartlett

    def test_to_dict(self):
        """Test dictionary conversion."""
        info = DetectionInfo(
            trigger_probability=0.88,
            peak_probability=0.95,
            bark_count_in_clip=5,
        )

        data = info.to_dict()

        assert data["trigger_probability"] == 0.88
        assert data["peak_probability"] == 0.95
        assert data["bark_count_in_clip"] == 5


class TestDeviceInfo:
    """Tests for DeviceInfo dataclass."""

    def test_defaults(self):
        """Test default values."""
        info = DeviceInfo()

        assert info.hostname  # Should have a hostname
        assert info.microphone == "Unknown"

    def test_to_dict(self):
        """Test dictionary conversion."""
        info = DeviceInfo(hostname="test-pi", microphone="ReSpeaker")

        data = info.to_dict()

        assert data["hostname"] == "test-pi"
        assert data["microphone"] == "ReSpeaker"


class TestEvidenceMetadata:
    """Tests for EvidenceMetadata dataclass."""

    def test_create(self):
        """Test metadata creation."""
        metadata = EvidenceMetadata.create(
            filename="test_bark.wav",
            duration_seconds=30.0,
            sample_rate=44100,
            channels=2,
            trigger_probability=0.88,
            peak_probability=0.95,
            bark_count=5,
            microphone_name="Test Mic",
            doa_bartlett=90,
        )

        assert metadata.filename == "test_bark.wav"
        assert metadata.duration_seconds == 30.0
        assert metadata.detection.trigger_probability == 0.88
        assert metadata.device.microphone == "Test Mic"

    def test_to_dict(self):
        """Test dictionary conversion."""
        metadata = EvidenceMetadata.create(
            filename="test_bark.wav",
            duration_seconds=30.0,
            sample_rate=44100,
            channels=2,
            trigger_probability=0.88,
            peak_probability=0.95,
            bark_count=5,
            microphone_name="Test Mic",
        )

        data = metadata.to_dict()

        assert data["filename"] == "test_bark.wav"
        assert data["duration_seconds"] == 30.0
        assert "detection" in data
        assert "device" in data

    def test_from_dict(self):
        """Test loading from dictionary."""
        original = EvidenceMetadata.create(
            filename="test_bark.wav",
            duration_seconds=30.0,
            sample_rate=44100,
            channels=2,
            trigger_probability=0.88,
            peak_probability=0.95,
            bark_count=5,
            microphone_name="Test Mic",
            doa_bartlett=90,
        )

        data = original.to_dict()
        loaded = EvidenceMetadata.from_dict(data)

        assert loaded.filename == original.filename
        assert loaded.duration_seconds == original.duration_seconds
        assert loaded.detection.trigger_probability == original.detection.trigger_probability


class TestEvidenceIndex:
    """Tests for EvidenceIndex dataclass."""

    def test_empty_index(self):
        """Test empty index."""
        index = EvidenceIndex()

        assert len(index.entries) == 0
        assert index.total_duration_seconds == 0.0
        assert index.total_bark_count == 0

    def test_add_entry(self):
        """Test adding entries."""
        index = EvidenceIndex()

        metadata = EvidenceMetadata.create(
            filename="test1.wav",
            duration_seconds=30.0,
            sample_rate=44100,
            channels=2,
            trigger_probability=0.88,
            peak_probability=0.95,
            bark_count=5,
            microphone_name="Test Mic",
        )

        index.add(metadata)

        assert len(index.entries) == 1
        assert index.total_duration_seconds == 30.0
        assert index.total_bark_count == 5

    def test_get_recent(self):
        """Test getting recent entries."""
        index = EvidenceIndex()

        for i in range(5):
            metadata = EvidenceMetadata.create(
                filename=f"test{i}.wav",
                duration_seconds=30.0,
                sample_rate=44100,
                channels=2,
                trigger_probability=0.88,
                peak_probability=0.95,
                bark_count=1,
                microphone_name="Test Mic",
            )
            index.add(metadata)

        recent = index.get_recent(3)

        assert len(recent) == 3
        # Most recent should be first
        assert recent[0].filename == "test4.wav"

    def test_to_dict_and_from_dict(self):
        """Test serialization round-trip."""
        index = EvidenceIndex()

        metadata = EvidenceMetadata.create(
            filename="test.wav",
            duration_seconds=30.0,
            sample_rate=44100,
            channels=2,
            trigger_probability=0.88,
            peak_probability=0.95,
            bark_count=5,
            microphone_name="Test Mic",
        )
        index.add(metadata)

        data = index.to_dict()
        loaded = EvidenceIndex.from_dict(data)

        assert len(loaded.entries) == 1
        assert loaded.entries[0].filename == "test.wav"
