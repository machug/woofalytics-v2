"""Tests for fingerprint matching module."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from woofalytics.fingerprint.matcher import (
    DEFAULT_THRESHOLD,
    HIGH_CONFIDENCE_THRESHOLD,
    LOW_CONFIDENCE_THRESHOLD,
    MEDIUM_CONFIDENCE_THRESHOLD,
    MIN_AUTO_TAG_MARGIN,
    MIN_CONFIDENCE_FOR_EMBEDDING_UPDATE,
    _get_confidence_tier,
)
from woofalytics.fingerprint.models import (
    BarkFingerprint,
    ConfidenceTier,
    DogProfile,
    FingerprintMatch,
)


class TestConfidenceTier:
    """Tests for ConfidenceTier enum and classification."""

    def test_confidence_tier_values(self):
        """Test that confidence tier enum has expected values."""
        assert ConfidenceTier.HIGH.value == "high"
        assert ConfidenceTier.MEDIUM.value == "medium"
        assert ConfidenceTier.LOW.value == "low"
        assert ConfidenceTier.NONE.value == "none"

    def test_confidence_threshold_ordering(self):
        """Test that thresholds are in descending order."""
        assert HIGH_CONFIDENCE_THRESHOLD > MEDIUM_CONFIDENCE_THRESHOLD
        assert MEDIUM_CONFIDENCE_THRESHOLD > LOW_CONFIDENCE_THRESHOLD
        assert LOW_CONFIDENCE_THRESHOLD > 0.0

    def test_default_threshold_is_medium(self):
        """Test that default threshold equals medium confidence threshold."""
        assert DEFAULT_THRESHOLD == MEDIUM_CONFIDENCE_THRESHOLD

    def test_get_confidence_tier_high(self):
        """Test high confidence tier classification."""
        assert _get_confidence_tier(0.95) == ConfidenceTier.HIGH
        assert _get_confidence_tier(0.90) == ConfidenceTier.HIGH
        assert _get_confidence_tier(1.0) == ConfidenceTier.HIGH

    def test_get_confidence_tier_medium(self):
        """Test medium confidence tier classification."""
        assert _get_confidence_tier(0.85) == ConfidenceTier.MEDIUM
        assert _get_confidence_tier(0.78) == ConfidenceTier.MEDIUM
        assert _get_confidence_tier(0.89) == ConfidenceTier.MEDIUM

    def test_get_confidence_tier_low(self):
        """Test low confidence tier classification."""
        assert _get_confidence_tier(0.70) == ConfidenceTier.LOW
        assert _get_confidence_tier(0.65) == ConfidenceTier.LOW
        assert _get_confidence_tier(0.77) == ConfidenceTier.LOW

    def test_get_confidence_tier_none(self):
        """Test none confidence tier classification."""
        assert _get_confidence_tier(0.60) == ConfidenceTier.NONE
        assert _get_confidence_tier(0.50) == ConfidenceTier.NONE
        assert _get_confidence_tier(0.0) == ConfidenceTier.NONE


class TestFingerprintMatch:
    """Tests for FingerprintMatch dataclass."""

    def test_match_creation(self):
        """Test creating a fingerprint match."""
        match = FingerprintMatch(
            dog_id="dog123",
            dog_name="Buddy",
            confidence=0.92,
            sample_count=10,
            confidence_tier=ConfidenceTier.HIGH,
            acoustic_score=0.88,
        )

        assert match.dog_id == "dog123"
        assert match.dog_name == "Buddy"
        assert match.confidence == 0.92
        assert match.sample_count == 10
        assert match.confidence_tier == ConfidenceTier.HIGH
        assert match.acoustic_score == 0.88

    def test_match_default_values(self):
        """Test default values for optional fields."""
        match = FingerprintMatch(
            dog_id="dog123",
            dog_name="Buddy",
            confidence=0.85,
            sample_count=5,
        )

        assert match.confidence_tier == ConfidenceTier.NONE
        assert match.acoustic_score is None

    def test_match_to_dict(self):
        """Test dictionary conversion."""
        match = FingerprintMatch(
            dog_id="dog123",
            dog_name="Buddy",
            confidence=0.9234,
            sample_count=10,
            confidence_tier=ConfidenceTier.HIGH,
            acoustic_score=0.8765,
        )

        data = match.to_dict()

        assert data["dog_id"] == "dog123"
        assert data["dog_name"] == "Buddy"
        assert data["confidence"] == 0.9234
        assert data["sample_count"] == 10
        assert data["confidence_tier"] == "high"
        assert data["acoustic_score"] == 0.8765


class TestDogProfile:
    """Tests for DogProfile model."""

    def test_can_auto_tag_requires_confirmation(self):
        """Test that unconfirmed dogs cannot auto-tag."""
        dog = DogProfile(
            id="dog123",
            name="Buddy",
            confirmed=False,
            sample_count=10,  # Enough samples
            min_samples_for_auto_tag=5,
        )

        assert not dog.can_auto_tag()

    def test_can_auto_tag_requires_min_samples(self):
        """Test that dogs need minimum samples to auto-tag."""
        dog = DogProfile(
            id="dog123",
            name="Buddy",
            confirmed=True,  # Confirmed
            sample_count=3,  # Not enough samples
            min_samples_for_auto_tag=5,
        )

        assert not dog.can_auto_tag()

    def test_can_auto_tag_success(self):
        """Test that confirmed dogs with enough samples can auto-tag."""
        dog = DogProfile(
            id="dog123",
            name="Buddy",
            confirmed=True,
            sample_count=5,
            min_samples_for_auto_tag=5,
        )

        assert dog.can_auto_tag()

    def test_update_embedding_first_sample(self):
        """Test embedding initialization on first sample."""
        dog = DogProfile(id="dog123", name="Buddy")
        embedding = np.array([1.0, 0.0, 0.0])

        dog.update_embedding(embedding)

        assert dog.sample_count == 1
        assert dog.embedding is not None
        # Should be normalized
        np.testing.assert_almost_equal(np.linalg.norm(dog.embedding), 1.0)

    def test_update_embedding_running_average(self):
        """Test that embeddings use weighted running average."""
        dog = DogProfile(id="dog123", name="Buddy")

        # First embedding: [1, 0, 0]
        dog.update_embedding(np.array([1.0, 0.0, 0.0]))
        assert dog.sample_count == 1

        # Second embedding: [0, 1, 0] - should blend with first
        dog.update_embedding(np.array([0.0, 1.0, 0.0]))
        assert dog.sample_count == 2

        # Result should be normalized and between the two
        assert dog.embedding is not None
        np.testing.assert_almost_equal(np.linalg.norm(dog.embedding), 1.0)
        # Direction should be roughly 45 degrees
        assert dog.embedding[0] > 0
        assert dog.embedding[1] > 0


class TestEmbeddingQualityGate:
    """Tests for embedding quality gate threshold."""

    def test_quality_gate_threshold_value(self):
        """Test that quality gate threshold is set correctly."""
        assert MIN_CONFIDENCE_FOR_EMBEDDING_UPDATE == 0.80

    def test_quality_gate_below_threshold(self):
        """Test that low-confidence matches are below quality gate."""
        low_confidence = 0.79
        assert low_confidence < MIN_CONFIDENCE_FOR_EMBEDDING_UPDATE

    def test_quality_gate_above_threshold(self):
        """Test that adequate matches pass quality gate."""
        good_confidence = 0.85
        assert good_confidence >= MIN_CONFIDENCE_FOR_EMBEDDING_UPDATE


class TestAutoTagMargin:
    """Tests for auto-tag margin threshold."""

    def test_margin_threshold_value(self):
        """Test that margin threshold is set correctly."""
        assert MIN_AUTO_TAG_MARGIN == 0.08

    def test_margin_sufficient(self):
        """Test sufficient margin calculation."""
        best_confidence = 0.85
        second_confidence = 0.75
        margin = best_confidence - second_confidence

        assert margin >= MIN_AUTO_TAG_MARGIN

    def test_margin_insufficient(self):
        """Test insufficient margin calculation."""
        best_confidence = 0.85
        second_confidence = 0.80
        margin = best_confidence - second_confidence

        assert margin < MIN_AUTO_TAG_MARGIN


class TestBarkFingerprint:
    """Tests for BarkFingerprint model."""

    def test_fingerprint_creation(self):
        """Test creating a bark fingerprint."""
        fp = BarkFingerprint(
            timestamp=datetime.now(UTC),
            detection_probability=0.95,
            doa_degrees=45,
            duration_ms=150.5,
            pitch_hz=800.0,
            spectral_centroid_hz=1500.0,
        )

        assert fp.id is not None
        assert len(fp.id) == 12  # UUID hex prefix
        assert fp.detection_probability == 0.95
        assert fp.doa_degrees == 45
        assert fp.duration_ms == 150.5
        assert fp.pitch_hz == 800.0
        assert fp.spectral_centroid_hz == 1500.0

    def test_fingerprint_untagged_defaults(self):
        """Test that new fingerprints are untagged by default."""
        fp = BarkFingerprint()

        assert fp.dog_id is None
        assert fp.match_confidence is None
        assert fp.cluster_id is None
        assert fp.confirmed is None
        assert fp.rejection_reason is None

    def test_fingerprint_to_dict(self):
        """Test dictionary conversion."""
        timestamp = datetime.now(UTC)
        fp = BarkFingerprint(
            timestamp=timestamp,
            dog_id="dog123",
            match_confidence=0.92,
            detection_probability=0.95,
            duration_ms=150.5,
        )

        data = fp.to_dict()

        assert data["dog_id"] == "dog123"
        assert data["match_confidence"] == 0.92
        assert data["detection_probability"] == 0.95
        assert data["duration_ms"] == 150.5
        assert data["timestamp"] == timestamp.isoformat()

    def test_fingerprint_from_dict_roundtrip(self):
        """Test from_dict correctly reconstructs fingerprint."""
        original = BarkFingerprint(
            timestamp=datetime.now(UTC),
            dog_id="dog123",
            match_confidence=0.92,
            detection_probability=0.95,
            duration_ms=150.5,
            pitch_hz=800.0,
        )

        data = original.to_dict()
        loaded = BarkFingerprint.from_dict(data)

        assert loaded.id == original.id
        assert loaded.dog_id == original.dog_id
        assert loaded.match_confidence == original.match_confidence
        assert loaded.detection_probability == original.detection_probability
        assert loaded.duration_ms == original.duration_ms
        assert loaded.pitch_hz == original.pitch_hz
