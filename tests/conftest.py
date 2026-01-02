"""Pytest fixtures for Woofalytics tests."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from woofalytics.config import (
    AudioConfig,
    DOAConfig,
    EvidenceConfig,
    ModelConfig,
    ServerConfig,
    Settings,
    WebhookConfig,
)
from woofalytics.audio.capture import AudioFrame


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings with sensible defaults."""
    return Settings(
        audio=AudioConfig(
            device_name="test_device",
            sample_rate=44100,
            channels=2,
            chunk_size=441,
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
            directory=Path("/tmp/woofalytics_test_evidence"),
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
def mock_audio_frame() -> AudioFrame:
    """Create a mock audio frame for testing."""
    # Generate 10ms of stereo audio at 44100Hz
    samples = 441
    channels = 2
    data = np.zeros((channels, samples), dtype=np.int16)

    # Add some random noise
    data = np.random.randint(-1000, 1000, (channels, samples), dtype=np.int16)

    return AudioFrame(
        timestamp=time.time(),
        data=data.T.flatten().tobytes(),
        channels=channels,
        sample_rate=44100,
    )


@pytest.fixture
def mock_audio_frames(mock_audio_frame: AudioFrame) -> list[AudioFrame]:
    """Create multiple mock audio frames."""
    frames = []
    base_time = time.time()

    for i in range(10):
        frame = AudioFrame(
            timestamp=base_time + (i * 0.01),
            data=mock_audio_frame.data,
            channels=mock_audio_frame.channels,
            sample_rate=mock_audio_frame.sample_rate,
        )
        frames.append(frame)

    return frames


@pytest.fixture
def mock_bark_event():
    """Create a mock bark event."""
    from woofalytics.detection.model import BarkEvent

    return BarkEvent(
        timestamp=datetime.now(),
        probability=0.95,
        is_barking=True,
        doa_bartlett=90,
        doa_capon=88,
        doa_mem=92,
    )


@pytest.fixture
def temp_evidence_dir(tmp_path: Path) -> Path:
    """Create a temporary evidence directory."""
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    return evidence_dir


@pytest.fixture
def mock_pyaudio():
    """Mock PyAudio for testing without audio hardware."""
    with patch("pyaudio.PyAudio") as mock:
        # Mock device info
        mock_instance = MagicMock()
        mock.return_value = mock_instance

        mock_instance.get_host_api_info_by_index.return_value = {
            "deviceCount": 2,
            "defaultInputDevice": 0,
        }

        mock_instance.get_device_info_by_index.side_effect = [
            {
                "name": "Test Microphone",
                "maxInputChannels": 2,
                "defaultSampleRate": 44100.0,
            },
            {
                "name": "ReSpeaker 2-Mic HAT",
                "maxInputChannels": 2,
                "defaultSampleRate": 48000.0,
            },
        ]

        yield mock


@pytest.fixture
def client(test_settings: Settings) -> Generator[TestClient, None, None]:
    """Create a test client for the FastAPI application."""
    from woofalytics.app import create_app

    # Create app with mocked dependencies
    with patch("woofalytics.app.load_settings", return_value=test_settings):
        with patch("woofalytics.app.BarkDetector"):
            with patch("woofalytics.app.EvidenceStorage"):
                app = create_app()
                with TestClient(app) as test_client:
                    yield test_client
