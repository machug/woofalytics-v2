"""Tests for detection modules."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pytest

from woofalytics.detection.doa import DirectionEstimator, angle_to_direction
from woofalytics.detection.model import BarkEvent


class TestDirectionEstimator:
    """Tests for DirectionEstimator class."""

    def test_initialization(self):
        """Test estimator initialization."""
        estimator = DirectionEstimator(
            element_spacing=0.1,
            num_elements=2,
            angle_min=0,
            angle_max=180,
        )

        assert estimator.element_spacing == 0.1
        assert estimator.num_elements == 2
        assert estimator.angle_min == 0
        assert estimator.angle_max == 180

    def test_scanning_angles(self):
        """Test scanning angle generation."""
        estimator = DirectionEstimator(
            angle_min=0,
            angle_max=180,
        )

        assert len(estimator._incident_angles) == 181  # 0 to 180 inclusive
        assert estimator._incident_angles[0] == 0
        assert estimator._incident_angles[-1] == 180

    def test_insufficient_channels(self):
        """Test behavior with single channel audio."""
        estimator = DirectionEstimator()  # Default method is bartlett

        # Single channel audio
        audio = np.random.randn(1, 1000).astype(np.float32)

        bartlett, capon, mem = estimator.estimate(audio)

        # Should return default front-facing angle for configured method only
        assert bartlett == 90  # bartlett is the default method
        assert capon is None
        assert mem is None

    def test_estimate_multichannel(self):
        """Test estimation with multichannel audio."""
        estimator = DirectionEstimator(num_elements=2)  # Default method is bartlett

        # Generate stereo audio with slight phase shift
        samples = 4410
        audio = np.random.randn(2, samples).astype(np.float32)

        bartlett, capon, mem = estimator.estimate(audio)

        # Should return valid angle for configured method only
        assert 0 <= bartlett <= 180  # bartlett is the default method
        assert capon is None
        assert mem is None

    def test_get_spectrum(self):
        """Test spectrum retrieval."""
        estimator = DirectionEstimator()

        audio = np.random.randn(2, 4410).astype(np.float32)

        angles, spectrum = estimator.get_spectrum(audio, method="bartlett")

        assert len(angles) == len(spectrum)
        assert len(angles) == 181

    def test_uca_initialization(self):
        """Test UCA (Uniform Circular Array) initialization."""
        estimator = DirectionEstimator(
            array_type="uca",
            num_elements=4,
            radius=0.093,
            angle_min=0,
            angle_max=359,
        )

        assert estimator.array_type == "uca"
        assert estimator.num_elements == 4
        assert estimator.radius == 0.093
        assert len(estimator._incident_angles) == 360

    def test_uca_estimate(self):
        """Test UCA DOA estimation with 4-mic array."""
        estimator = DirectionEstimator(
            array_type="uca",
            num_elements=4,
            radius=0.093,
            angle_min=0,
            angle_max=359,
        )

        # 4-channel audio
        audio = np.random.randn(4, 4410).astype(np.float32)

        angle = estimator.estimate_single(audio)

        # Should return valid 360° angle
        assert 0 <= angle <= 359


class TestAngleToDirection:
    """Tests for angle_to_direction function."""

    def test_far_left(self):
        assert angle_to_direction(0) == "far left"
        assert angle_to_direction(15) == "far left"
        assert angle_to_direction(29) == "far left"

    def test_left(self):
        assert angle_to_direction(30) == "left"
        assert angle_to_direction(45) == "left"
        assert angle_to_direction(59) == "left"

    def test_front(self):
        assert angle_to_direction(60) == "front"
        assert angle_to_direction(90) == "front"
        assert angle_to_direction(119) == "front"

    def test_right(self):
        assert angle_to_direction(120) == "right"
        assert angle_to_direction(135) == "right"
        assert angle_to_direction(149) == "right"

    def test_far_right(self):
        assert angle_to_direction(150) == "far right"
        assert angle_to_direction(165) == "far right"
        assert angle_to_direction(180) == "far right"

    def test_circular_front(self):
        """Test 360° circular directions - front."""
        assert angle_to_direction(0, is_circular=True) == "front"
        assert angle_to_direction(350, is_circular=True) == "front"
        assert angle_to_direction(10, is_circular=True) == "front"

    def test_circular_sides(self):
        """Test 360° circular directions - sides."""
        assert angle_to_direction(90, is_circular=True) == "right"
        assert angle_to_direction(270, is_circular=True) == "left"

    def test_circular_back(self):
        """Test 360° circular directions - back."""
        assert angle_to_direction(180, is_circular=True) == "back"
        assert angle_to_direction(170, is_circular=True) == "back"
        assert angle_to_direction(190, is_circular=True) == "back"

    def test_circular_diagonals(self):
        """Test 360° circular directions - diagonals."""
        assert angle_to_direction(45, is_circular=True) == "front-right"
        assert angle_to_direction(135, is_circular=True) == "back-right"
        assert angle_to_direction(225, is_circular=True) == "back-left"
        assert angle_to_direction(315, is_circular=True) == "front-left"


class TestBarkEvent:
    """Tests for BarkEvent dataclass."""

    def test_creation(self):
        """Test event creation."""
        event = BarkEvent(
            timestamp=datetime.now(),
            probability=0.95,
            is_barking=True,
            doa_bartlett=90,
            doa_capon=88,
            doa_mem=92,
        )

        assert event.probability == 0.95
        assert event.is_barking is True
        assert event.doa_bartlett == 90

    def test_to_dict(self):
        """Test dictionary conversion."""
        now = datetime.now()
        event = BarkEvent(
            timestamp=now,
            probability=0.95,
            is_barking=True,
            doa_bartlett=90,
        )

        data = event.to_dict()

        assert data["probability"] == 0.95
        assert data["is_barking"] is True
        assert data["doa_bartlett"] == 90
        assert data["timestamp"] == now.isoformat()

    def test_no_doa(self):
        """Test event without DOA data."""
        event = BarkEvent(
            timestamp=datetime.now(),
            probability=0.5,
            is_barking=False,
        )

        assert event.doa_bartlett is None
        assert event.doa_capon is None
        assert event.doa_mem is None
