"""Tests for bark summary report API endpoints.

Tests cover daily, weekly, and monthly summary functionality.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from woofalytics.config import (
    Settings,
    AudioConfig,
    ModelConfig,
    DOAConfig,
    EvidenceConfig,
    ServerConfig,
    WebhookConfig,
)
from woofalytics.evidence.metadata import (
    EvidenceMetadata,
    DetectionInfo,
    DeviceInfo,
)


@pytest.fixture
def api_settings(tmp_path: Path) -> Settings:
    """Create settings for API testing."""
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    return Settings(
        audio=AudioConfig(
            device_name="test_device",
            sample_rate=48000,
            channels=2,
            chunk_size=480,
            volume_percent=75,
        ),
        model=ModelConfig(
            path=Path("./models/traced_model.pt"),
            threshold=0.88,
        ),
        doa=DOAConfig(
            enabled=True,
            num_elements=2,
        ),
        evidence=EvidenceConfig(
            directory=evidence_dir,
        ),
        webhook=WebhookConfig(
            enabled=False,
        ),
        server=ServerConfig(
            host="127.0.0.1",
            port=8000,
        ),
        log_level="DEBUG",
    )


def create_mock_entry(
    timestamp: datetime,
    peak_prob: float = 0.95,
    bark_count: int = 3,
    filename: str = "test.wav",
) -> EvidenceMetadata:
    """Create a mock EvidenceMetadata entry."""
    return EvidenceMetadata(
        filename=filename,
        timestamp_utc=timestamp,
        timestamp_local=timestamp,
        duration_seconds=5.0,
        sample_rate=48000,
        channels=2,
        detection=DetectionInfo(
            trigger_probability=0.90,
            peak_probability=peak_prob,
            bark_count_in_clip=bark_count,
            doa_bartlett=90,
        ),
        device=DeviceInfo(hostname="test-host", microphone="Test Mic"),
    )


@pytest.fixture
def mock_evidence_with_entries() -> MagicMock:
    """Create a mock EvidenceStorage with entries across multiple days."""
    evidence = MagicMock()

    # Create test entries spanning multiple days
    # Base time: Monday 2026-01-05 12:00 UTC
    base_time = datetime(2026, 1, 5, 12, 0, 0, tzinfo=timezone.utc)
    entries = [
        # Monday - 3 entries at different hours
        create_mock_entry(
            base_time.replace(hour=8),
            peak_prob=0.95,
            bark_count=5,
            filename="bark_mon_08.wav",
        ),
        create_mock_entry(
            base_time.replace(hour=14),
            peak_prob=0.88,
            bark_count=3,
            filename="bark_mon_14.wav",
        ),
        create_mock_entry(
            base_time.replace(hour=14, minute=30),
            peak_prob=0.92,
            bark_count=4,
            filename="bark_mon_14b.wav",
        ),
        # Tuesday - 2 entries
        create_mock_entry(
            base_time + timedelta(days=1, hours=-3),  # Tuesday 09:00
            peak_prob=0.85,
            bark_count=2,
            filename="bark_tue_09.wav",
        ),
        create_mock_entry(
            base_time + timedelta(days=1, hours=6),  # Tuesday 18:00
            peak_prob=0.91,
            bark_count=6,
            filename="bark_tue_18.wav",
        ),
        # Wednesday - 1 entry
        create_mock_entry(
            base_time + timedelta(days=2),  # Wednesday 12:00
            peak_prob=0.89,
            bark_count=3,
            filename="bark_wed_12.wav",
        ),
    ]

    evidence._index = MagicMock()
    evidence._index.entries = entries

    return evidence


@pytest.fixture
def mock_empty_evidence() -> MagicMock:
    """Create a mock EvidenceStorage with no entries."""
    evidence = MagicMock()
    evidence._index = MagicMock()
    evidence._index.entries = []
    return evidence


@pytest.fixture
def mock_detector() -> MagicMock:
    """Create a mock BarkDetector."""
    detector = MagicMock()
    detector.is_running = True
    detector.uptime_seconds = 3600.0
    detector.total_barks_detected = 42
    return detector


@pytest.fixture
def mock_fingerprint_store() -> MagicMock:
    """Create a mock FingerprintStore."""
    store = MagicMock()
    store.list_dogs.return_value = []
    return store


@pytest.fixture
def summary_client(
    api_settings: Settings,
    mock_detector: MagicMock,
    mock_evidence_with_entries: MagicMock,
    mock_fingerprint_store: MagicMock,
) -> Generator[TestClient, None, None]:
    """Create a test client for summary testing."""
    from woofalytics.api.routes import router
    from woofalytics.api.websocket import ConnectionManager
    from woofalytics.api.ratelimit import setup_rate_limiting, configure_rate_limits

    app = FastAPI()

    configure_rate_limits(enabled=False)
    setup_rate_limiting(app)

    app.include_router(router, prefix="/api")

    app.state.settings = api_settings
    app.state.detector = mock_detector
    app.state.evidence = mock_evidence_with_entries
    app.state.fingerprint_store = mock_fingerprint_store
    app.state.ws_manager = ConnectionManager()

    with TestClient(app) as client:
        yield client


@pytest.fixture
def empty_summary_client(
    api_settings: Settings,
    mock_detector: MagicMock,
    mock_empty_evidence: MagicMock,
    mock_fingerprint_store: MagicMock,
) -> Generator[TestClient, None, None]:
    """Create a test client with empty evidence."""
    from woofalytics.api.routes import router
    from woofalytics.api.websocket import ConnectionManager
    from woofalytics.api.ratelimit import setup_rate_limiting, configure_rate_limits

    app = FastAPI()

    configure_rate_limits(enabled=False)
    setup_rate_limiting(app)

    app.include_router(router, prefix="/api")

    app.state.settings = api_settings
    app.state.detector = mock_detector
    app.state.evidence = mock_empty_evidence
    app.state.fingerprint_store = mock_fingerprint_store
    app.state.ws_manager = ConnectionManager()

    with TestClient(app) as client:
        yield client


class TestDailySummary:
    """Tests for /api/summary/daily endpoint."""

    def test_daily_summary_returns_stats(self, summary_client: TestClient) -> None:
        """Test daily summary returns correct statistics."""
        response = summary_client.get("/api/summary/daily?date=2026-01-05")
        assert response.status_code == 200

        data = response.json()
        assert data["date"] == "2026-01-05"
        # Monday has 3 entries with bark counts: 5 + 3 + 4 = 12
        assert data["total_barks"] == 12
        assert data["total_events"] == 3
        assert data["total_duration_seconds"] == 15.0  # 3 * 5.0

    def test_daily_summary_hourly_breakdown(self, summary_client: TestClient) -> None:
        """Test daily summary includes hourly breakdown."""
        response = summary_client.get("/api/summary/daily?date=2026-01-05")
        assert response.status_code == 200

        data = response.json()
        hourly = data["hourly_breakdown"]
        # Hour 8 has 5 barks, hour 14 has 3 + 4 = 7 barks
        assert hourly["8"] == 5
        assert hourly["14"] == 7

    def test_daily_summary_peak_hour(self, summary_client: TestClient) -> None:
        """Test daily summary identifies peak hour correctly."""
        response = summary_client.get("/api/summary/daily?date=2026-01-05")
        assert response.status_code == 200

        data = response.json()
        # Hour 14 has the most barks (7)
        assert data["peak_hour"] == 14

    def test_daily_summary_avg_confidence(self, summary_client: TestClient) -> None:
        """Test daily summary calculates average confidence."""
        response = summary_client.get("/api/summary/daily?date=2026-01-05")
        assert response.status_code == 200

        data = response.json()
        # (0.95 + 0.88 + 0.92) / 3 = 0.9166...
        assert 0.91 <= data["avg_confidence"] <= 0.92

    def test_daily_summary_empty_day(self, summary_client: TestClient) -> None:
        """Test daily summary for a day with no events."""
        response = summary_client.get("/api/summary/daily?date=2026-01-10")
        assert response.status_code == 200

        data = response.json()
        assert data["total_barks"] == 0
        assert data["total_events"] == 0
        assert data["peak_hour"] is None
        assert data["hourly_breakdown"] == {}

    def test_daily_summary_invalid_date(self, summary_client: TestClient) -> None:
        """Test daily summary rejects invalid date format."""
        response = summary_client.get("/api/summary/daily?date=invalid")
        assert response.status_code == 400
        assert "Invalid date format" in response.json()["detail"]

    def test_daily_summary_empty_evidence(
        self, empty_summary_client: TestClient
    ) -> None:
        """Test daily summary with no evidence data."""
        response = empty_summary_client.get("/api/summary/daily?date=2026-01-05")
        assert response.status_code == 200

        data = response.json()
        assert data["total_barks"] == 0
        assert data["total_events"] == 0


class TestWeeklySummary:
    """Tests for /api/summary/weekly endpoint."""

    def test_weekly_summary_returns_stats(self, summary_client: TestClient) -> None:
        """Test weekly summary returns correct statistics."""
        # Any date in the week of 2026-01-05 (Mon-Sun)
        response = summary_client.get("/api/summary/weekly?date=2026-01-05")
        assert response.status_code == 200

        data = response.json()
        # All 6 entries are in this week
        # Total barks: 5 + 3 + 4 + 2 + 6 + 3 = 23
        assert data["total_barks"] == 23
        assert data["total_events"] == 6
        assert data["total_duration_seconds"] == 30.0  # 6 * 5.0

    def test_weekly_summary_daily_breakdown(self, summary_client: TestClient) -> None:
        """Test weekly summary includes daily breakdown."""
        response = summary_client.get("/api/summary/weekly?date=2026-01-05")
        assert response.status_code == 200

        data = response.json()
        daily = data["daily_breakdown"]
        # Monday: 5 + 3 + 4 = 12
        assert daily["2026-01-05"] == 12
        # Tuesday: 2 + 6 = 8
        assert daily["2026-01-06"] == 8
        # Wednesday: 3
        assert daily["2026-01-07"] == 3

    def test_weekly_summary_week_boundaries(self, summary_client: TestClient) -> None:
        """Test weekly summary has correct week boundaries."""
        response = summary_client.get("/api/summary/weekly?date=2026-01-07")
        assert response.status_code == 200

        data = response.json()
        # Week should start on Monday 2026-01-05
        assert "2026-01-05" in data["week_start"]
        # Week should end on Sunday 2026-01-11
        assert "2026-01-11" in data["week_end"]

    def test_weekly_summary_empty_week(self, summary_client: TestClient) -> None:
        """Test weekly summary for a week with no events."""
        response = summary_client.get("/api/summary/weekly?date=2026-01-20")
        assert response.status_code == 200

        data = response.json()
        assert data["total_barks"] == 0
        assert data["daily_breakdown"] == {}

    def test_weekly_summary_invalid_date(self, summary_client: TestClient) -> None:
        """Test weekly summary rejects invalid date format."""
        response = summary_client.get("/api/summary/weekly?date=2026/01/05")
        assert response.status_code == 400


class TestMonthlySummary:
    """Tests for /api/summary/monthly endpoint."""

    def test_monthly_summary_returns_stats(self, summary_client: TestClient) -> None:
        """Test monthly summary returns correct statistics."""
        response = summary_client.get("/api/summary/monthly?month=2026-01")
        assert response.status_code == 200

        data = response.json()
        assert data["month"] == "2026-01"
        # All 6 entries are in January 2026
        assert data["total_barks"] == 23
        assert data["total_events"] == 6

    def test_monthly_summary_daily_breakdown(self, summary_client: TestClient) -> None:
        """Test monthly summary includes daily breakdown."""
        response = summary_client.get("/api/summary/monthly?month=2026-01")
        assert response.status_code == 200

        data = response.json()
        daily = data["daily_breakdown"]
        assert "2026-01-05" in daily
        assert "2026-01-06" in daily
        assert "2026-01-07" in daily

    def test_monthly_summary_empty_month(self, summary_client: TestClient) -> None:
        """Test monthly summary for a month with no events."""
        response = summary_client.get("/api/summary/monthly?month=2026-02")
        assert response.status_code == 200

        data = response.json()
        assert data["total_barks"] == 0
        assert data["daily_breakdown"] == {}

    def test_monthly_summary_invalid_month(self, summary_client: TestClient) -> None:
        """Test monthly summary rejects invalid month format."""
        response = summary_client.get("/api/summary/monthly?month=January2026")
        assert response.status_code == 400
        assert "Invalid month format" in response.json()["detail"]

    def test_monthly_summary_empty_evidence(
        self, empty_summary_client: TestClient
    ) -> None:
        """Test monthly summary with no evidence data."""
        response = empty_summary_client.get("/api/summary/monthly?month=2026-01")
        assert response.status_code == 200

        data = response.json()
        assert data["total_barks"] == 0
        assert data["total_events"] == 0
