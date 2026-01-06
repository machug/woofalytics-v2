"""Tests for REST API routes.

This module provides comprehensive tests for all FastAPI REST endpoints.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from woofalytics.config import Settings, AudioConfig, ModelConfig, DOAConfig, EvidenceConfig, ServerConfig, WebhookConfig
from woofalytics.detection.model import BarkEvent


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


@pytest.fixture
def mock_detector() -> MagicMock:
    """Create a mock BarkDetector."""
    detector = MagicMock()
    detector.is_running = True
    detector.uptime_seconds = 3600.0
    detector.total_barks_detected = 42
    detector.total_barks = 42
    detector.get_status.return_value = {
        "running": True,
        "uptime_seconds": 3600.0,
        "total_barks": 42,
        "microphone": "Test Microphone",
        "vad_stats": {
            "passed_count": 100,
            "skipped_count": 900,
            "total_count": 1000,
            "skip_rate": 0.9,
        },
        "yamnet_stats": {
            "passed": 80,
            "skipped": 20,
            "total": 100,
            "skip_rate": 0.2,
        },
    }
    detector.get_last_event.return_value = BarkEvent(
        timestamp=datetime(2026, 1, 6, 12, 0, 0),
        probability=0.95,
        is_barking=True,
        doa_bartlett=90,
        doa_capon=88,
        doa_mem=92,
    )
    detector.get_recent_events.return_value = [
        BarkEvent(
            timestamp=datetime(2026, 1, 6, 12, 0, 0),
            probability=0.95,
            is_barking=True,
        ),
        BarkEvent(
            timestamp=datetime(2026, 1, 6, 11, 55, 0),
            probability=0.87,
            is_barking=True,
        ),
    ]
    return detector


@pytest.fixture
def mock_evidence() -> MagicMock:
    """Create a mock EvidenceStorage."""
    evidence = MagicMock()
    evidence.total_recordings = 100
    evidence.get_stats.return_value = {
        "total_recordings": 100,
        "total_duration_seconds": 500.0,
        "total_barks_recorded": 42,
    }

    # Create mock evidence metadata
    mock_recording = MagicMock()
    mock_recording.filename = "bark_20260106_120000.wav"
    mock_recording.timestamp_utc = datetime(2026, 1, 6, 12, 0, 0)
    mock_recording.timestamp_local = datetime(2026, 1, 6, 12, 0, 0)
    mock_recording.duration_seconds = 5.0
    mock_recording.sample_rate = 48000
    mock_recording.channels = 2
    mock_recording.detection.trigger_probability = 0.95
    mock_recording.detection.peak_probability = 0.98
    mock_recording.detection.bark_count_in_clip = 3
    mock_recording.detection.doa_degrees = 90

    evidence.get_recent_evidence.return_value = [mock_recording]
    evidence.get_evidence_by_date.return_value = [mock_recording]

    return evidence


@pytest.fixture
def mock_fingerprint_store() -> MagicMock:
    """Create a mock FingerprintStore."""
    store = MagicMock()

    # Mock dog profiles
    mock_dog = MagicMock()
    mock_dog.id = "dog-001"
    mock_dog.name = "Buddy"
    mock_dog.notes = "Golden retriever"
    mock_dog.created_at = datetime(2026, 1, 1)
    mock_dog.updated_at = datetime(2026, 1, 5)
    mock_dog.confirmed = False
    mock_dog.confirmed_at = None
    mock_dog.min_samples_for_auto_tag = 5
    mock_dog.can_auto_tag.return_value = False
    mock_dog.sample_count = 3
    mock_dog.first_seen = datetime(2026, 1, 1)
    mock_dog.last_seen = datetime(2026, 1, 5)
    mock_dog.total_barks = 10
    mock_dog.avg_duration_ms = 250.0
    mock_dog.avg_pitch_hz = 500.0

    store.list_dogs.return_value = [mock_dog]
    store.get_dog.return_value = mock_dog
    store.create_dog.return_value = mock_dog
    store.update_dog.return_value = mock_dog
    store.delete_dog.return_value = True
    store.merge_dogs.return_value = True
    store.confirm_dog.return_value = mock_dog
    store.unconfirm_dog.return_value = mock_dog

    # Mock fingerprints
    mock_fingerprint = MagicMock()
    mock_fingerprint.id = "fp-001"
    mock_fingerprint.timestamp = datetime(2026, 1, 6, 12, 0, 0)
    mock_fingerprint.dog_id = "dog-001"
    mock_fingerprint.match_confidence = 0.95
    mock_fingerprint.cluster_id = None
    mock_fingerprint.evidence_filename = "bark_20260106_120000.wav"
    mock_fingerprint.detection_probability = 0.95
    mock_fingerprint.doa_degrees = 90
    mock_fingerprint.duration_ms = 250.0
    mock_fingerprint.pitch_hz = 500.0
    mock_fingerprint.spectral_centroid_hz = 2000.0
    mock_fingerprint.embedding = [0.1] * 512

    store.get_fingerprint.return_value = mock_fingerprint
    store.get_fingerprints_for_dog.return_value = [mock_fingerprint]
    store.get_untagged_fingerprints.return_value = []
    store.tag_fingerprint.return_value = True
    store.untag_fingerprint.return_value = True
    store.list_fingerprints.return_value = ([mock_fingerprint], 1)
    store.get_stats.return_value = {
        "dogs": 5,
        "fingerprints": 100,
        "untagged": 20,
        "clusters": 3,
    }
    store.get_dog_acoustic_aggregates.return_value = [
        {
            "dog_id": "dog-001",
            "dog_name": "Buddy",
            "avg_pitch_hz": 500.0,
            "min_pitch_hz": 400.0,
            "max_pitch_hz": 600.0,
            "avg_duration_ms": 250.0,
            "min_duration_ms": 100.0,
            "max_duration_ms": 400.0,
            "avg_spectral_centroid_hz": 2000.0,
            "total_barks": 10,
            "first_seen": datetime(2026, 1, 1),
            "last_seen": datetime(2026, 1, 5),
        }
    ]
    store.delete_fingerprint.return_value = True
    store.purge_fingerprints.return_value = 5
    store.recalculate_dog_bark_counts.return_value = 3

    return store


@pytest.fixture
def api_client(
    api_settings: Settings,
    mock_detector: MagicMock,
    mock_evidence: MagicMock,
    mock_fingerprint_store: MagicMock,
) -> Generator[TestClient, None, None]:
    """Create a test client with mocked dependencies."""
    from woofalytics.api.routes import router
    from woofalytics.api.websocket import ConnectionManager
    from woofalytics.api.ratelimit import setup_rate_limiting

    app = FastAPI()

    # Set up rate limiting
    setup_rate_limiting(app)

    app.include_router(router, prefix="/api")

    # Set up app state
    app.state.settings = api_settings
    app.state.detector = mock_detector
    app.state.evidence = mock_evidence
    app.state.fingerprint_store = mock_fingerprint_store
    app.state.ws_manager = ConnectionManager()

    with TestClient(app) as client:
        yield client


# --- Health & Status Tests ---


class TestHealthEndpoint:
    """Tests for /api/health endpoint."""

    def test_health_check_healthy(self, api_client: TestClient) -> None:
        """Test health check returns healthy status."""
        response = api_client.get("/api/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["uptime_seconds"] == 3600.0
        assert data["total_barks_detected"] == 42
        assert data["evidence_files_count"] == 100

    def test_health_check_degraded(
        self,
        api_client: TestClient,
        mock_detector: MagicMock,
    ) -> None:
        """Test health check returns degraded when detector not running."""
        mock_detector.is_running = False

        response = api_client.get("/api/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "degraded"


class TestStatusEndpoint:
    """Tests for /api/status endpoint."""

    def test_get_status(self, api_client: TestClient) -> None:
        """Test status endpoint returns detector status."""
        response = api_client.get("/api/status")
        assert response.status_code == 200

        data = response.json()
        assert data["running"] is True
        assert data["uptime_seconds"] == 3600.0
        assert data["total_barks"] == 42
        assert data["microphone"] == "Test Microphone"

        # Check VAD stats
        assert data["vad_stats"]["passed"] == 100
        assert data["vad_stats"]["skipped"] == 900

        # Check YAMNet stats
        assert data["yamnet_stats"]["passed"] == 80
        assert data["yamnet_stats"]["skipped"] == 20

        # Check last event
        assert data["last_event"]["probability"] == 0.95
        assert data["last_event"]["is_barking"] is True


# --- Bark Detection Tests ---


class TestBarkEndpoints:
    """Tests for bark detection endpoints."""

    def test_get_last_bark(self, api_client: TestClient) -> None:
        """Test getting last bark event."""
        response = api_client.get("/api/bark")
        assert response.status_code == 200

        data = response.json()
        assert data["probability"] == 0.95
        assert data["is_barking"] is True
        assert data["doa_bartlett"] == 90

    def test_get_last_bark_none(
        self,
        api_client: TestClient,
        mock_detector: MagicMock,
    ) -> None:
        """Test getting last bark when none exists."""
        mock_detector.get_last_event.return_value = None

        response = api_client.get("/api/bark")
        assert response.status_code == 200
        assert response.json() is None

    def test_get_bark_probability(self, api_client: TestClient) -> None:
        """Test getting bark probability."""
        response = api_client.get("/api/bark/probability")
        assert response.status_code == 200

        data = response.json()
        assert data["probability"] == 0.95

    def test_get_bark_probability_none(
        self,
        api_client: TestClient,
        mock_detector: MagicMock,
    ) -> None:
        """Test bark probability when no event."""
        mock_detector.get_last_event.return_value = None

        response = api_client.get("/api/bark/probability")
        assert response.status_code == 200
        assert response.json()["probability"] is None

    def test_get_recent_barks(self, api_client: TestClient) -> None:
        """Test getting recent bark events."""
        response = api_client.get("/api/bark/recent")
        assert response.status_code == 200

        data = response.json()
        assert data["count"] == 2
        assert len(data["events"]) == 2

    def test_get_recent_barks_with_count(
        self,
        api_client: TestClient,
        mock_detector: MagicMock,
    ) -> None:
        """Test getting recent barks with custom count."""
        response = api_client.get("/api/bark/recent?count=50")
        assert response.status_code == 200
        mock_detector.get_recent_events.assert_called_with(50)

    def test_get_recent_barks_invalid_count(self, api_client: TestClient) -> None:
        """Test recent barks with invalid count."""
        response = api_client.get("/api/bark/recent?count=0")
        assert response.status_code == 422  # Validation error

        response = api_client.get("/api/bark/recent?count=101")
        assert response.status_code == 422


# --- Evidence Tests ---


class TestEvidenceEndpoints:
    """Tests for evidence endpoints."""

    def test_list_evidence(self, api_client: TestClient) -> None:
        """Test listing evidence files."""
        response = api_client.get("/api/evidence")
        assert response.status_code == 200

        data = response.json()
        assert data["count"] == 1
        assert len(data["evidence"]) == 1
        assert data["evidence"][0]["filename"] == "bark_20260106_120000.wav"

    def test_list_evidence_with_count(
        self,
        api_client: TestClient,
        mock_evidence: MagicMock,
    ) -> None:
        """Test listing evidence with custom count."""
        response = api_client.get("/api/evidence?count=50")
        assert response.status_code == 200
        mock_evidence.get_recent_evidence.assert_called_with(50)

    def test_get_evidence_stats(self, api_client: TestClient) -> None:
        """Test getting evidence statistics."""
        response = api_client.get("/api/evidence/stats")
        assert response.status_code == 200

        data = response.json()
        assert data["total_recordings"] == 100
        assert data["total_duration_seconds"] == 500.0

    def test_download_evidence_invalid_filename(self, api_client: TestClient) -> None:
        """Test downloading with path traversal attempt."""
        # Test with backslash
        response = api_client.get("/api/evidence/test\\file.wav")
        assert response.status_code == 400
        assert "Invalid filename" in response.json()["detail"]

    def test_download_evidence_invalid_type(self, api_client: TestClient) -> None:
        """Test downloading non-allowed file type."""
        response = api_client.get("/api/evidence/test.exe")
        assert response.status_code == 400
        assert "Invalid file type" in response.json()["detail"]

    def test_download_evidence_not_found(
        self,
        api_client: TestClient,
        api_settings: Settings,
    ) -> None:
        """Test downloading non-existent file."""
        response = api_client.get("/api/evidence/nonexistent.wav")
        assert response.status_code == 404

    def test_download_evidence_success(
        self,
        api_client: TestClient,
        api_settings: Settings,
    ) -> None:
        """Test successfully downloading evidence file."""
        # Create a test file
        test_file = api_settings.evidence.directory / "test_bark.wav"
        test_file.write_bytes(b"RIFF" + b"\x00" * 100)  # Fake WAV header

        response = api_client.get("/api/evidence/test_bark.wav")
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"

    def test_get_evidence_by_date(self, api_client: TestClient) -> None:
        """Test getting evidence by date."""
        response = api_client.get("/api/evidence/date/2026-01-06")
        assert response.status_code == 200

        data = response.json()
        assert data["count"] == 1

    def test_get_evidence_by_date_invalid(self, api_client: TestClient) -> None:
        """Test getting evidence with invalid date format."""
        response = api_client.get("/api/evidence/date/invalid-date")
        assert response.status_code == 400
        assert "Invalid date format" in response.json()["detail"]


# --- Configuration Tests ---


class TestConfigEndpoint:
    """Tests for configuration endpoint."""

    def test_get_config(self, api_client: TestClient) -> None:
        """Test getting sanitized configuration."""
        response = api_client.get("/api/config")
        assert response.status_code == 200

        data = response.json()

        # Check audio config
        assert data["audio"]["sample_rate"] == 48000
        assert data["audio"]["channels"] == 2

        # Check model config
        assert data["model"]["threshold"] == 0.88

        # Check DOA config
        assert data["doa"]["enabled"] is True

        # Verify paths are not exposed
        assert "path" not in data["model"]
        assert "directory" not in data["evidence"]


# --- Direction Tests ---


class TestDirectionEndpoint:
    """Tests for DOA direction endpoint."""

    def test_get_direction(self, api_client: TestClient) -> None:
        """Test getting direction of arrival."""
        response = api_client.get("/api/direction")
        assert response.status_code == 200

        data = response.json()
        assert data["available"] is True
        assert data["bartlett"]["angle"] == 90
        # 90 degrees (60-120 range) maps to "front"
        assert data["bartlett"]["direction"] == "front"

    def test_get_direction_unavailable(
        self,
        api_client: TestClient,
        mock_detector: MagicMock,
    ) -> None:
        """Test direction when DOA data unavailable."""
        mock_detector.get_last_event.return_value = None

        response = api_client.get("/api/direction")
        assert response.status_code == 200

        data = response.json()
        assert data["available"] is False


# --- Dog Profile Tests ---


class TestDogEndpoints:
    """Tests for dog profile endpoints."""

    def test_list_dogs(self, api_client: TestClient) -> None:
        """Test listing all dogs."""
        response = api_client.get("/api/dogs")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Buddy"

    def test_create_dog(
        self,
        api_client: TestClient,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test creating a new dog."""
        response = api_client.post(
            "/api/dogs",
            json={"name": "Max", "notes": "Labrador"},
        )
        assert response.status_code == 201
        mock_fingerprint_store.create_dog.assert_called_once()

    def test_get_dog(self, api_client: TestClient) -> None:
        """Test getting a specific dog."""
        response = api_client.get("/api/dogs/dog-001")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == "dog-001"
        assert data["name"] == "Buddy"

    def test_get_dog_not_found(
        self,
        api_client: TestClient,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test getting non-existent dog."""
        mock_fingerprint_store.get_dog.return_value = None

        response = api_client.get("/api/dogs/nonexistent")
        assert response.status_code == 404

    def test_update_dog(
        self,
        api_client: TestClient,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test updating a dog."""
        response = api_client.put(
            "/api/dogs/dog-001",
            json={"name": "Buddy Jr", "notes": "Updated notes"},
        )
        assert response.status_code == 200
        mock_fingerprint_store.update_dog.assert_called_once()

    def test_update_dog_not_found(
        self,
        api_client: TestClient,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test updating non-existent dog."""
        mock_fingerprint_store.update_dog.return_value = None

        response = api_client.put(
            "/api/dogs/nonexistent",
            json={"name": "Test"},
        )
        assert response.status_code == 404

    def test_delete_dog(
        self,
        api_client: TestClient,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test deleting a dog."""
        response = api_client.delete("/api/dogs/dog-001")
        assert response.status_code == 204
        mock_fingerprint_store.delete_dog.assert_called_once()

    def test_delete_dog_not_found(
        self,
        api_client: TestClient,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test deleting non-existent dog."""
        mock_fingerprint_store.delete_dog.return_value = False

        response = api_client.delete("/api/dogs/nonexistent")
        assert response.status_code == 404

    def test_merge_dogs(
        self,
        api_client: TestClient,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test merging two dogs."""
        response = api_client.post("/api/dogs/dog-001/merge/dog-002")
        assert response.status_code == 200
        mock_fingerprint_store.merge_dogs.assert_called_once()

    def test_merge_dogs_same(self, api_client: TestClient) -> None:
        """Test merging dog with itself."""
        response = api_client.post("/api/dogs/dog-001/merge/dog-001")
        assert response.status_code == 400
        assert "Cannot merge a dog with itself" in response.json()["detail"]

    def test_get_dog_barks(self, api_client: TestClient) -> None:
        """Test getting barks for a dog."""
        response = api_client.get("/api/dogs/dog-001/barks")
        assert response.status_code == 200

        data = response.json()
        assert data["dog_id"] == "dog-001"
        assert data["dog_name"] == "Buddy"

    def test_confirm_dog(
        self,
        api_client: TestClient,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test confirming a dog for auto-tagging."""
        response = api_client.post(
            "/api/dogs/dog-001/confirm",
            json={},
        )
        assert response.status_code == 200
        mock_fingerprint_store.confirm_dog.assert_called_once()

    def test_unconfirm_dog(
        self,
        api_client: TestClient,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test removing confirmation from dog."""
        response = api_client.post("/api/dogs/dog-001/unconfirm")
        assert response.status_code == 200
        mock_fingerprint_store.unconfirm_dog.assert_called_once()


# --- Bark Tagging Tests ---


class TestBarkTaggingEndpoints:
    """Tests for bark tagging endpoints."""

    def test_list_untagged_barks(self, api_client: TestClient) -> None:
        """Test listing untagged barks."""
        response = api_client.get("/api/barks/untagged")
        assert response.status_code == 200

        data = response.json()
        assert "count" in data
        assert "total_untagged" in data

    def test_tag_bark(
        self,
        api_client: TestClient,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test tagging a bark."""
        response = api_client.post(
            "/api/barks/fp-001/tag",
            json={"dog_id": "dog-001", "confidence": 0.95},
        )
        assert response.status_code == 200
        mock_fingerprint_store.tag_fingerprint.assert_called_once()

    def test_tag_bark_not_found(
        self,
        api_client: TestClient,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test tagging non-existent bark."""
        mock_fingerprint_store.get_fingerprint.return_value = None

        response = api_client.post(
            "/api/barks/nonexistent/tag",
            json={"dog_id": "dog-001"},
        )
        assert response.status_code == 404

    def test_bulk_tag_barks(
        self,
        api_client: TestClient,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test bulk tagging barks."""
        response = api_client.post(
            "/api/barks/bulk-tag",
            json={
                "bark_ids": ["fp-001", "fp-002"],
                "dog_id": "dog-001",
                "confidence": 0.9,
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert "tagged_count" in data

    def test_correct_bark(
        self,
        api_client: TestClient,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test correcting a bark identification."""
        response = api_client.post(
            "/api/barks/fp-001/correct",
            json={"new_dog_id": "dog-002"},
        )
        assert response.status_code == 200

    def test_untag_bark(
        self,
        api_client: TestClient,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test untagging a bark."""
        response = api_client.post("/api/barks/fp-001/untag")
        assert response.status_code == 200
        mock_fingerprint_store.untag_fingerprint.assert_called_once()


# --- Fingerprint Tests ---


class TestFingerprintEndpoints:
    """Tests for fingerprint endpoints."""

    def test_list_fingerprints(self, api_client: TestClient) -> None:
        """Test listing fingerprints."""
        response = api_client.get("/api/fingerprints")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

    def test_list_fingerprints_with_filters(
        self,
        api_client: TestClient,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test listing fingerprints with filters."""
        response = api_client.get(
            "/api/fingerprints?dog_id=dog-001&tagged=true&min_confidence=0.8"
        )
        assert response.status_code == 200

    def test_get_fingerprint_stats(self, api_client: TestClient) -> None:
        """Test getting fingerprint statistics."""
        response = api_client.get("/api/fingerprints/stats")
        assert response.status_code == 200

        data = response.json()
        assert data["dogs"] == 5
        assert data["fingerprints"] == 100
        assert data["untagged"] == 20
        assert data["clusters"] == 3

    def test_get_fingerprint_aggregates(self, api_client: TestClient) -> None:
        """Test getting fingerprint aggregates."""
        response = api_client.get("/api/fingerprints/aggregates")
        assert response.status_code == 200

        data = response.json()
        assert "dogs" in data
        assert len(data["dogs"]) == 1
        assert data["dogs"][0]["dog_name"] == "Buddy"


# --- Maintenance Tests ---


class TestMaintenanceEndpoints:
    """Tests for maintenance endpoints."""

    def test_delete_fingerprint(
        self,
        api_client: TestClient,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test deleting a fingerprint."""
        response = api_client.delete("/api/fingerprints/fp-001")
        assert response.status_code == 204
        mock_fingerprint_store.delete_fingerprint.assert_called_once()

    def test_delete_fingerprint_not_found(
        self,
        api_client: TestClient,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test deleting non-existent fingerprint."""
        mock_fingerprint_store.delete_fingerprint.return_value = False

        response = api_client.delete("/api/fingerprints/nonexistent")
        assert response.status_code == 404

    def test_purge_fingerprints(
        self,
        api_client: TestClient,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test purging fingerprints."""
        response = api_client.post(
            "/api/maintenance/purge-fingerprints",
            json={"before": "2026-01-01T00:00:00", "untagged_only": True},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["deleted_count"] == 5
        assert data["resource_type"] == "fingerprints"

    def test_purge_fingerprints_requires_filter(
        self,
        api_client: TestClient,
    ) -> None:
        """Test purge requires at least one filter."""
        response = api_client.post(
            "/api/maintenance/purge-fingerprints",
            json={},
        )
        assert response.status_code == 400

    def test_purge_evidence(
        self,
        api_client: TestClient,
        mock_evidence: MagicMock,
    ) -> None:
        """Test purging evidence files."""
        mock_evidence.purge_evidence = AsyncMock(return_value=10)

        response = api_client.post(
            "/api/maintenance/purge-evidence",
            json={"before": "2026-01-01T00:00:00"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["resource_type"] == "evidence"

    def test_purge_evidence_requires_filter(self, api_client: TestClient) -> None:
        """Test purge evidence requires date filter."""
        response = api_client.post(
            "/api/maintenance/purge-evidence",
            json={},
        )
        assert response.status_code == 400

    def test_recalculate_bark_counts(
        self,
        api_client: TestClient,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test recalculating bark counts."""
        response = api_client.post("/api/maintenance/recalculate-bark-counts")
        assert response.status_code == 200

        data = response.json()
        assert data["updated_count"] == 3
        mock_fingerprint_store.recalculate_dog_bark_counts.assert_called_once()


# --- Metrics Tests ---


class TestMetricsEndpoint:
    """Tests for Prometheus metrics endpoint."""

    def test_get_metrics(self, api_client: TestClient) -> None:
        """Test getting Prometheus metrics."""
        with patch("woofalytics.api.routes.get_metrics") as mock_get_metrics, \
             patch("woofalytics.api.routes.generate_latest") as mock_generate:

            mock_metrics = MagicMock()
            mock_metrics.is_initialized = True
            mock_get_metrics.return_value = mock_metrics
            mock_generate.return_value = b"# HELP test_metric\ntest_metric 42"

            response = api_client.get("/api/metrics")
            assert response.status_code == 200
            assert "text/plain" in response.headers["content-type"]


# --- Rate Limiting Tests ---


class TestRateLimiting:
    """Tests for rate limiting middleware."""

    def test_rate_limit_headers_present(self, api_client: TestClient) -> None:
        """Test that rate limit headers are included in responses."""
        response = api_client.get("/api/health")
        assert response.status_code == 200

        # Middleware should add rate limit headers
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    def test_rate_limit_exceeded(
        self,
        api_settings: Settings,
        mock_detector: MagicMock,
        mock_evidence: MagicMock,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test that rate limiting returns 429 when exceeded."""
        from woofalytics.api.routes import router
        from woofalytics.api.websocket import ConnectionManager
        from woofalytics.api.ratelimit import (
            setup_rate_limiting,
            configure_rate_limits,
            RateLimitMiddleware,
        )

        app = FastAPI()

        # Configure very low rate limit for testing
        configure_rate_limits(read="3/minute", enabled=True)
        setup_rate_limiting(app)

        app.include_router(router, prefix="/api")

        # Set up app state
        app.state.settings = api_settings
        app.state.detector = mock_detector
        app.state.evidence = mock_evidence
        app.state.fingerprint_store = mock_fingerprint_store
        app.state.ws_manager = ConnectionManager()

        with TestClient(app) as client:
            # First requests should succeed
            for i in range(3):
                response = client.get("/api/health")
                assert response.status_code == 200, f"Request {i+1} should succeed"

            # Next request should be rate limited
            response = client.get("/api/health")
            assert response.status_code == 429
            assert "Rate limit exceeded" in response.json()["detail"]
            assert "Retry-After" in response.headers

        # Reset rate limits for other tests
        configure_rate_limits(read="120/minute", enabled=True)

    def test_rate_limiting_can_be_disabled(
        self,
        api_settings: Settings,
        mock_detector: MagicMock,
        mock_evidence: MagicMock,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test that rate limiting can be disabled via configuration."""
        from woofalytics.api.routes import router
        from woofalytics.api.websocket import ConnectionManager
        from woofalytics.api.ratelimit import (
            setup_rate_limiting,
            configure_rate_limits,
        )

        app = FastAPI()

        # Disable rate limiting
        configure_rate_limits(read="1/minute", enabled=False)
        setup_rate_limiting(app)

        app.include_router(router, prefix="/api")

        # Set up app state
        app.state.settings = api_settings
        app.state.detector = mock_detector
        app.state.evidence = mock_evidence
        app.state.fingerprint_store = mock_fingerprint_store
        app.state.ws_manager = ConnectionManager()

        with TestClient(app) as client:
            # All requests should succeed when disabled
            for i in range(5):
                response = client.get("/api/health")
                assert response.status_code == 200

        # Re-enable rate limits for other tests
        configure_rate_limits(read="120/minute", enabled=True)

    def test_write_operations_have_lower_limit(
        self,
        api_settings: Settings,
        mock_detector: MagicMock,
        mock_evidence: MagicMock,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test that POST/PUT/DELETE use write limits (lower than read)."""
        from woofalytics.api.routes import router
        from woofalytics.api.websocket import ConnectionManager
        from woofalytics.api.ratelimit import (
            setup_rate_limiting,
            configure_rate_limits,
        )

        app = FastAPI()

        # Set read high, write low
        configure_rate_limits(read="100/minute", write="2/minute", enabled=True)
        setup_rate_limiting(app)

        app.include_router(router, prefix="/api")

        # Set up app state
        app.state.settings = api_settings
        app.state.detector = mock_detector
        app.state.evidence = mock_evidence
        app.state.fingerprint_store = mock_fingerprint_store
        app.state.ws_manager = ConnectionManager()

        with TestClient(app) as client:
            # Write operations should hit limit quickly
            for i in range(2):
                response = client.post(
                    "/api/dogs",
                    json={"name": f"Dog {i}", "notes": "test"},
                )
                assert response.status_code == 201

            # Third POST should be rate limited
            response = client.post(
                "/api/dogs",
                json={"name": "Dog 3", "notes": "test"},
            )
            assert response.status_code == 429

        # Reset rate limits
        configure_rate_limits(read="120/minute", write="30/minute", enabled=True)


# --- Authentication Tests ---


class TestAuthentication:
    """Tests for API key authentication middleware."""

    def test_public_endpoint_no_auth_required(
        self,
        api_settings: Settings,
        mock_detector: MagicMock,
        mock_evidence: MagicMock,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test that public endpoints work without authentication."""
        from woofalytics.api.routes import router
        from woofalytics.api.websocket import ConnectionManager
        from woofalytics.api.ratelimit import setup_rate_limiting, configure_rate_limits
        from woofalytics.api.auth import setup_auth, configure_auth

        app = FastAPI()

        # Enable auth with a test key
        configure_auth("test-api-key-12345")
        configure_rate_limits(enabled=False)
        setup_auth(app)
        setup_rate_limiting(app)

        app.include_router(router, prefix="/api")

        app.state.settings = api_settings
        app.state.detector = mock_detector
        app.state.evidence = mock_evidence
        app.state.fingerprint_store = mock_fingerprint_store
        app.state.ws_manager = ConnectionManager()

        with TestClient(app) as client:
            # Health endpoint should work without auth
            response = client.get("/api/health")
            assert response.status_code == 200

            # Metrics endpoint should work without auth
            with patch("woofalytics.api.routes.get_metrics") as mock_get_metrics, \
                 patch("woofalytics.api.routes.generate_latest") as mock_generate:
                mock_metrics = MagicMock()
                mock_metrics.is_initialized = True
                mock_get_metrics.return_value = mock_metrics
                mock_generate.return_value = b"# test metrics"
                response = client.get("/api/metrics")
                assert response.status_code == 200

        # Reset auth
        configure_auth(None)

    def test_protected_endpoint_requires_auth(
        self,
        api_settings: Settings,
        mock_detector: MagicMock,
        mock_evidence: MagicMock,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test that protected endpoints require authentication."""
        from woofalytics.api.routes import router
        from woofalytics.api.websocket import ConnectionManager
        from woofalytics.api.ratelimit import setup_rate_limiting, configure_rate_limits
        from woofalytics.api.auth import setup_auth, configure_auth

        app = FastAPI()

        # Enable auth with a test key
        configure_auth("test-api-key-12345")
        configure_rate_limits(enabled=False)
        setup_auth(app)
        setup_rate_limiting(app)

        app.include_router(router, prefix="/api")

        app.state.settings = api_settings
        app.state.detector = mock_detector
        app.state.evidence = mock_evidence
        app.state.fingerprint_store = mock_fingerprint_store
        app.state.ws_manager = ConnectionManager()

        with TestClient(app) as client:
            # Protected endpoint without auth header
            response = client.get("/api/status")
            assert response.status_code == 401
            assert "Missing Authorization" in response.json()["detail"]
            assert "WWW-Authenticate" in response.headers

        # Reset auth
        configure_auth(None)

    def test_protected_endpoint_with_invalid_key(
        self,
        api_settings: Settings,
        mock_detector: MagicMock,
        mock_evidence: MagicMock,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test that invalid API key returns 401."""
        from woofalytics.api.routes import router
        from woofalytics.api.websocket import ConnectionManager
        from woofalytics.api.ratelimit import setup_rate_limiting, configure_rate_limits
        from woofalytics.api.auth import setup_auth, configure_auth

        app = FastAPI()

        # Enable auth with a test key
        configure_auth("correct-api-key")
        configure_rate_limits(enabled=False)
        setup_auth(app)
        setup_rate_limiting(app)

        app.include_router(router, prefix="/api")

        app.state.settings = api_settings
        app.state.detector = mock_detector
        app.state.evidence = mock_evidence
        app.state.fingerprint_store = mock_fingerprint_store
        app.state.ws_manager = ConnectionManager()

        with TestClient(app) as client:
            # Wrong API key
            response = client.get(
                "/api/status",
                headers={"Authorization": "Bearer wrong-key"},
            )
            assert response.status_code == 401
            assert "Invalid API key" in response.json()["detail"]

            # Invalid format (no Bearer prefix)
            response = client.get(
                "/api/status",
                headers={"Authorization": "wrong-key"},
            )
            assert response.status_code == 401
            assert "Invalid Authorization format" in response.json()["detail"]

        # Reset auth
        configure_auth(None)

    def test_protected_endpoint_with_valid_key(
        self,
        api_settings: Settings,
        mock_detector: MagicMock,
        mock_evidence: MagicMock,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test that valid API key allows access."""
        from woofalytics.api.routes import router
        from woofalytics.api.websocket import ConnectionManager
        from woofalytics.api.ratelimit import setup_rate_limiting, configure_rate_limits
        from woofalytics.api.auth import setup_auth, configure_auth

        app = FastAPI()

        api_key = "valid-test-api-key"
        configure_auth(api_key)
        configure_rate_limits(enabled=False)
        setup_auth(app)
        setup_rate_limiting(app)

        app.include_router(router, prefix="/api")

        app.state.settings = api_settings
        app.state.detector = mock_detector
        app.state.evidence = mock_evidence
        app.state.fingerprint_store = mock_fingerprint_store
        app.state.ws_manager = ConnectionManager()

        with TestClient(app) as client:
            # Valid API key should work
            response = client.get(
                "/api/status",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            assert response.status_code == 200

            # Also test POST endpoint
            response = client.post(
                "/api/dogs",
                json={"name": "Test Dog", "notes": "test"},
                headers={"Authorization": f"Bearer {api_key}"},
            )
            assert response.status_code == 201

        # Reset auth
        configure_auth(None)

    def test_auth_disabled_allows_all_requests(
        self,
        api_settings: Settings,
        mock_detector: MagicMock,
        mock_evidence: MagicMock,
        mock_fingerprint_store: MagicMock,
    ) -> None:
        """Test that disabled authentication allows all requests."""
        from woofalytics.api.routes import router
        from woofalytics.api.websocket import ConnectionManager
        from woofalytics.api.ratelimit import setup_rate_limiting, configure_rate_limits
        from woofalytics.api.auth import setup_auth, configure_auth

        app = FastAPI()

        # Disable auth
        configure_auth(None)
        configure_rate_limits(enabled=False)
        setup_auth(app)
        setup_rate_limiting(app)

        app.include_router(router, prefix="/api")

        app.state.settings = api_settings
        app.state.detector = mock_detector
        app.state.evidence = mock_evidence
        app.state.fingerprint_store = mock_fingerprint_store
        app.state.ws_manager = ConnectionManager()

        with TestClient(app) as client:
            # Should work without auth when disabled
            response = client.get("/api/status")
            assert response.status_code == 200

            # Empty string should also disable
            configure_auth("")
            response = client.get("/api/status")
            assert response.status_code == 200

        # Reset auth
        configure_auth(None)
