"""Tests for data export API endpoints.

Tests cover JSON and CSV export functionality with filtering.
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
    EvidenceIndex,
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
    """Create a mock EvidenceStorage with index entries."""
    evidence = MagicMock()

    # Create test entries with different timestamps and confidences
    base_time = datetime(2026, 1, 6, 12, 0, 0, tzinfo=timezone.utc)
    entries = [
        create_mock_entry(
            base_time - timedelta(hours=2),
            peak_prob=0.95,
            filename="bark_001.wav",
        ),
        create_mock_entry(
            base_time - timedelta(hours=1),
            peak_prob=0.75,
            filename="bark_002.wav",
        ),
        create_mock_entry(
            base_time,
            peak_prob=0.88,
            filename="bark_003.wav",
        ),
    ]

    # Set up the _index with entries
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
def export_client(
    api_settings: Settings,
    mock_detector: MagicMock,
    mock_evidence_with_entries: MagicMock,
    mock_fingerprint_store: MagicMock,
) -> Generator[TestClient, None, None]:
    """Create a test client for export testing."""
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
def empty_export_client(
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


class TestExportJson:
    """Tests for /api/export/json endpoint."""

    def test_export_json_returns_all_events(self, export_client: TestClient) -> None:
        """Test JSON export returns all events by default."""
        response = export_client.get("/api/export/json")
        assert response.status_code == 200

        data = response.json()
        assert data["count"] == 3
        assert len(data["entries"]) == 3
        assert "exported_at" in data
        assert "filters" in data

    def test_export_json_filters_by_confidence(
        self, export_client: TestClient
    ) -> None:
        """Test JSON export filters by minimum confidence."""
        response = export_client.get("/api/export/json?min_confidence=0.80")
        assert response.status_code == 200

        data = response.json()
        # Only entries with peak_probability >= 0.80 (0.95 and 0.88)
        assert data["count"] == 2

        # Verify all entries meet threshold
        for entry in data["entries"]:
            assert entry["peak_probability"] >= 0.80

    def test_export_json_filters_by_date_range(
        self, export_client: TestClient
    ) -> None:
        """Test JSON export filters by date range."""
        # Filter to only include the middle entry (1 hour before base time)
        start = "2026-01-06T10:30:00Z"
        end = "2026-01-06T11:30:00Z"

        response = export_client.get(f"/api/export/json?start_date={start}&end_date={end}")
        assert response.status_code == 200

        data = response.json()
        assert data["count"] == 1
        assert data["entries"][0]["filename"] == "bark_002.wav"

    def test_export_json_entry_structure(self, export_client: TestClient) -> None:
        """Test JSON export entries have correct structure."""
        response = export_client.get("/api/export/json")
        assert response.status_code == 200

        entry = response.json()["entries"][0]
        assert "timestamp_utc" in entry
        assert "timestamp_local" in entry
        assert "duration_seconds" in entry
        assert "trigger_probability" in entry
        assert "peak_probability" in entry
        assert "bark_count" in entry
        assert "doa_degrees" in entry
        assert "filename" in entry

    def test_export_json_empty_result(self, empty_export_client: TestClient) -> None:
        """Test JSON export with no data returns empty array."""
        response = empty_export_client.get("/api/export/json")
        assert response.status_code == 200

        data = response.json()
        assert data["count"] == 0
        assert data["entries"] == []

    def test_export_json_invalid_confidence(self, export_client: TestClient) -> None:
        """Test JSON export rejects invalid confidence values."""
        response = export_client.get("/api/export/json?min_confidence=1.5")
        assert response.status_code == 422  # Validation error

        response = export_client.get("/api/export/json?min_confidence=-0.1")
        assert response.status_code == 422


class TestExportCsv:
    """Tests for /api/export/csv endpoint."""

    def test_export_csv_downloads_file(self, export_client: TestClient) -> None:
        """Test CSV export returns downloadable file."""
        response = export_client.get("/api/export/csv")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert "attachment" in response.headers["content-disposition"]
        assert ".csv" in response.headers["content-disposition"]

    def test_export_csv_has_correct_headers(self, export_client: TestClient) -> None:
        """Test CSV export has correct column headers."""
        response = export_client.get("/api/export/csv")
        assert response.status_code == 200

        lines = response.text.strip().split("\n")
        header = lines[0].strip()  # Strip \r from Windows-style line endings

        expected_columns = [
            "timestamp_utc",
            "timestamp_local",
            "duration_seconds",
            "trigger_probability",
            "peak_probability",
            "bark_count",
            "doa_degrees",
            "filename",
        ]
        assert header == ",".join(expected_columns)

    def test_export_csv_has_correct_row_count(self, export_client: TestClient) -> None:
        """Test CSV export has correct number of data rows."""
        response = export_client.get("/api/export/csv")
        assert response.status_code == 200

        lines = response.text.strip().split("\n")
        # 1 header + 3 data rows
        assert len(lines) == 4

    def test_export_csv_filters_work(self, export_client: TestClient) -> None:
        """Test CSV export respects filter parameters."""
        response = export_client.get("/api/export/csv?min_confidence=0.90")
        assert response.status_code == 200

        lines = response.text.strip().split("\n")
        # 1 header + 1 data row (only 0.95 confidence entry)
        assert len(lines) == 2

    def test_export_csv_empty_result(self, empty_export_client: TestClient) -> None:
        """Test CSV export with no data returns header only."""
        response = empty_export_client.get("/api/export/csv")
        assert response.status_code == 200

        lines = response.text.strip().split("\n")
        # Just the header row
        assert len(lines) == 1
        assert "timestamp_utc" in lines[0]


class TestExportStats:
    """Tests for /api/export/stats endpoint."""

    def test_export_stats_returns_totals(self, export_client: TestClient) -> None:
        """Test stats endpoint returns correct totals."""
        response = export_client.get("/api/export/stats")
        assert response.status_code == 200

        data = response.json()
        assert data["total_entries"] == 3
        assert data["total_barks"] == 9  # 3 entries * 3 barks each
        assert data["total_duration_seconds"] == 15.0  # 3 entries * 5.0 seconds

    def test_export_stats_filters_work(self, export_client: TestClient) -> None:
        """Test stats endpoint respects filters."""
        response = export_client.get("/api/export/stats?min_confidence=0.90")
        assert response.status_code == 200

        data = response.json()
        assert data["total_entries"] == 1

    def test_export_stats_date_range(self, export_client: TestClient) -> None:
        """Test stats shows date range of filtered data."""
        response = export_client.get("/api/export/stats")
        assert response.status_code == 200

        data = response.json()
        assert data["date_range_start"] is not None
        assert data["date_range_end"] is not None

    def test_export_stats_empty(self, empty_export_client: TestClient) -> None:
        """Test stats with no data."""
        response = empty_export_client.get("/api/export/stats")
        assert response.status_code == 200

        data = response.json()
        assert data["total_entries"] == 0
        assert data["total_barks"] == 0
        assert data["date_range_start"] is None
        assert data["date_range_end"] is None
