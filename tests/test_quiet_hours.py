"""Tests for quiet hours configuration and time-based sensitivity adjustment."""

from __future__ import annotations

from datetime import time

import pytest
from freezegun import freeze_time

from woofalytics.config import QuietHoursConfig


class TestQuietHoursConfig:
    """Tests for QuietHoursConfig model."""

    def test_defaults(self):
        """Test default values."""
        config = QuietHoursConfig()

        assert config.enabled is False
        assert config.start == time(22, 0)
        assert config.end == time(6, 0)
        assert config.threshold == 0.9
        assert config.notifications is False
        assert config.timezone == "UTC"

    def test_time_string_parsing(self):
        """Test HH:MM string parsing for start/end times."""
        config = QuietHoursConfig(start="23:30", end="07:00")

        assert config.start == time(23, 30)
        assert config.end == time(7, 0)

    def test_invalid_time_string_rejected(self):
        """Test that invalid time strings are rejected."""
        with pytest.raises(ValueError, match="Invalid time format"):
            QuietHoursConfig(start="25:00")

        with pytest.raises(ValueError, match="Invalid time format"):
            QuietHoursConfig(start="not-a-time")

    def test_threshold_validation(self):
        """Test threshold must be between 0.0 and 1.0."""
        config = QuietHoursConfig(threshold=0.0)
        assert config.threshold == 0.0

        config = QuietHoursConfig(threshold=1.0)
        assert config.threshold == 1.0

        with pytest.raises(ValueError):
            QuietHoursConfig(threshold=-0.1)

        with pytest.raises(ValueError):
            QuietHoursConfig(threshold=1.1)

    def test_invalid_timezone_rejected(self):
        """Test that invalid timezone names are rejected."""
        with pytest.raises(ValueError, match="Invalid timezone"):
            QuietHoursConfig(timezone="Not/A/Timezone")

        with pytest.raises(ValueError, match="Invalid timezone"):
            QuietHoursConfig(timezone="PST")  # Abbreviations not accepted

    def test_valid_timezones_accepted(self):
        """Test that valid IANA timezone names are accepted."""
        config = QuietHoursConfig(timezone="Australia/Sydney")
        assert config.timezone == "Australia/Sydney"

        config = QuietHoursConfig(timezone="America/New_York")
        assert config.timezone == "America/New_York"

        config = QuietHoursConfig(timezone="UTC")
        assert config.timezone == "UTC"


class TestQuietHoursIsActive:
    """Tests for QuietHoursConfig.is_active() method."""

    @pytest.fixture
    def config(self):
        """Standard quiet hours config: 22:00-06:00 UTC."""
        return QuietHoursConfig(
            enabled=True,
            start="22:00",
            end="06:00",
            timezone="UTC",
        )

    def test_disabled_returns_false(self):
        """Test that disabled config always returns False."""
        config = QuietHoursConfig(enabled=False, start="00:00", end="23:59")
        with freeze_time("2026-01-11 12:00:00"):
            assert config.is_active() is False

    @pytest.mark.parametrize("time_str,expected", [
        ("2026-01-11 22:00:00", True),   # Exact start - IN quiet hours
        ("2026-01-11 21:59:59", False),  # Just before start - NOT in quiet hours
        ("2026-01-12 06:00:00", False),  # Exact end - NOT in quiet hours (exclusive)
        ("2026-01-12 05:59:59", True),   # Just before end - IN quiet hours
        ("2026-01-12 00:00:00", True),   # Midnight - IN quiet hours
        ("2026-01-11 12:00:00", False),  # Noon - NOT in quiet hours
        ("2026-01-11 23:30:00", True),   # Late night - IN quiet hours
        ("2026-01-12 03:00:00", True),   # Early morning - IN quiet hours
    ])
    def test_midnight_crossing_boundaries(self, config, time_str, expected):
        """Test time range that crosses midnight (22:00-06:00)."""
        with freeze_time(time_str):
            assert config.is_active() == expected

    def test_same_day_range(self):
        """Test non-midnight-crossing range (09:00-17:00)."""
        config = QuietHoursConfig(
            enabled=True,
            start="09:00",
            end="17:00",
            timezone="UTC",
        )

        with freeze_time("2026-01-11 12:00:00"):
            assert config.is_active() is True

        with freeze_time("2026-01-11 08:59:59"):
            assert config.is_active() is False

        with freeze_time("2026-01-11 17:00:00"):
            assert config.is_active() is False

        with freeze_time("2026-01-11 20:00:00"):
            assert config.is_active() is False

    def test_timezone_conversion(self):
        """Test that timezone is correctly applied."""
        # Sydney is UTC+11 in January (AEDT)
        config = QuietHoursConfig(
            enabled=True,
            start="22:00",  # 10 PM Sydney
            end="06:00",    # 6 AM Sydney
            timezone="Australia/Sydney",
        )

        # 11 PM Sydney = 12 PM UTC (previous day)
        with freeze_time("2026-01-10 12:00:00"):
            assert config.is_active() is True

        # 7 AM Sydney = 8 PM UTC (previous day)
        with freeze_time("2026-01-10 20:00:00"):
            assert config.is_active() is False


class TestQuietHoursGetThreshold:
    """Tests for QuietHoursConfig.get_threshold() method."""

    @pytest.fixture
    def config(self):
        """Quiet hours config with 0.9 threshold."""
        return QuietHoursConfig(
            enabled=True,
            start="22:00",
            end="06:00",
            threshold=0.9,
            timezone="UTC",
        )

    def test_returns_quiet_threshold_when_active(self, config):
        """Test that quiet hours threshold is returned when active."""
        with freeze_time("2026-01-11 23:00:00"):
            assert config.get_threshold(0.5) == 0.9

    def test_returns_default_when_not_active(self, config):
        """Test that default threshold is returned when not in quiet hours."""
        with freeze_time("2026-01-11 12:00:00"):
            assert config.get_threshold(0.5) == 0.5

    def test_returns_default_when_disabled(self):
        """Test that default threshold is returned when disabled."""
        config = QuietHoursConfig(
            enabled=False,
            threshold=0.9,
        )
        with freeze_time("2026-01-11 23:00:00"):
            assert config.get_threshold(0.5) == 0.5
