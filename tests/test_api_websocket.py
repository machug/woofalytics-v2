"""Tests for WebSocket endpoints.

This module provides comprehensive tests for WebSocket functionality
including the ConnectionManager and all WebSocket endpoints.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from woofalytics.api.websocket import (
    ConnectionManager,
    bark_event_to_message,
    broadcast_bark_event,
)
from woofalytics.config import Settings, AudioConfig, ModelConfig, DOAConfig, EvidenceConfig, ServerConfig, WebhookConfig
from woofalytics.detection.model import BarkEvent


@pytest.fixture
def ws_settings(tmp_path: Path) -> Settings:
    """Create settings for WebSocket testing."""
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
    """Create a mock BarkDetector for WebSocket tests."""
    detector = MagicMock()
    detector.is_running = True
    detector.uptime_seconds = 3600.0
    detector.total_barks_detected = 42
    detector.get_status.return_value = {
        "running": True,
        "uptime_seconds": 3600.0,
        "total_barks": 42,
        "microphone": "Test Microphone",
    }
    detector.get_pipeline_state.return_value = {
        "stage": "bark_detected",
        "vad": {"passed": True, "level_db": -25.3, "threshold_db": -40.0},
        "yamnet": {"passed": True, "dog_probability": 0.42, "threshold": 0.05},
        "clap": {"probability": 0.85, "is_barking": True},
        "stats": {"vad_skipped": 100, "yamnet_skipped": 50, "total_barks": 42},
    }
    detector.audio_capture = None  # Disable audio for basic tests
    return detector


@pytest.fixture
def connection_manager() -> ConnectionManager:
    """Create a ConnectionManager instance."""
    return ConnectionManager()


@pytest.fixture
def ws_client(
    ws_settings: Settings,
    mock_detector: MagicMock,
) -> Generator[TestClient, None, None]:
    """Create a test client with WebSocket support."""
    from woofalytics.api.websocket import router, ConnectionManager

    app = FastAPI()
    app.include_router(router)

    # Set up app state
    ws_manager = ConnectionManager()
    app.state.settings = ws_settings
    app.state.detector = mock_detector
    app.state.ws_manager = ws_manager

    with TestClient(app) as client:
        yield client


# --- ConnectionManager Tests ---


class TestConnectionManager:
    """Tests for the ConnectionManager class."""

    @pytest.mark.asyncio
    async def test_connect(self, connection_manager: ConnectionManager) -> None:
        """Test connecting a WebSocket."""
        mock_ws = AsyncMock(spec=WebSocket)

        await connection_manager.connect(mock_ws)

        assert mock_ws in connection_manager.active_connections
        assert connection_manager.connection_count == 1
        mock_ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect(self, connection_manager: ConnectionManager) -> None:
        """Test disconnecting a WebSocket."""
        mock_ws = AsyncMock(spec=WebSocket)

        await connection_manager.connect(mock_ws)
        assert connection_manager.connection_count == 1

        await connection_manager.disconnect(mock_ws)

        assert mock_ws not in connection_manager.active_connections
        assert connection_manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_not_connected(
        self,
        connection_manager: ConnectionManager,
    ) -> None:
        """Test disconnecting a WebSocket that isn't connected."""
        mock_ws = AsyncMock(spec=WebSocket)

        # Should not raise
        await connection_manager.disconnect(mock_ws)
        assert connection_manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_broadcast(self, connection_manager: ConnectionManager) -> None:
        """Test broadcasting to multiple connections."""
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)

        await connection_manager.connect(mock_ws1)
        await connection_manager.connect(mock_ws2)

        message = {"type": "test", "data": "hello"}
        await connection_manager.broadcast(message)

        mock_ws1.send_json.assert_called_once_with(message)
        mock_ws2.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_broadcast_removes_failed_connections(
        self,
        connection_manager: ConnectionManager,
    ) -> None:
        """Test that broadcast removes failed connections."""
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)

        # First connection succeeds, second fails
        mock_ws2.send_json.side_effect = Exception("Connection lost")

        await connection_manager.connect(mock_ws1)
        await connection_manager.connect(mock_ws2)
        assert connection_manager.connection_count == 2

        await connection_manager.broadcast({"type": "test"})

        # Failed connection should be removed
        assert connection_manager.connection_count == 1
        assert mock_ws1 in connection_manager.active_connections
        assert mock_ws2 not in connection_manager.active_connections

    @pytest.mark.asyncio
    async def test_send_personal_success(
        self,
        connection_manager: ConnectionManager,
    ) -> None:
        """Test sending personal message successfully."""
        mock_ws = AsyncMock(spec=WebSocket)
        await connection_manager.connect(mock_ws)

        message = {"type": "test"}
        result = await connection_manager.send_personal(mock_ws, message)

        assert result is True
        mock_ws.send_json.assert_called_with(message)

    @pytest.mark.asyncio
    async def test_send_personal_failure(
        self,
        connection_manager: ConnectionManager,
    ) -> None:
        """Test sending personal message with failure."""
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.send_json.side_effect = Exception("Connection lost")
        await connection_manager.connect(mock_ws)

        result = await connection_manager.send_personal(mock_ws, {"type": "test"})

        assert result is False
        # Connection should be removed
        assert mock_ws not in connection_manager.active_connections

    @pytest.mark.asyncio
    async def test_connection_count(
        self,
        connection_manager: ConnectionManager,
    ) -> None:
        """Test connection count property."""
        assert connection_manager.connection_count == 0

        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)

        await connection_manager.connect(mock_ws1)
        assert connection_manager.connection_count == 1

        await connection_manager.connect(mock_ws2)
        assert connection_manager.connection_count == 2

        await connection_manager.disconnect(mock_ws1)
        assert connection_manager.connection_count == 1


# --- Helper Function Tests ---


class TestBarkEventToMessage:
    """Tests for bark_event_to_message conversion."""

    def test_basic_bark_event(self) -> None:
        """Test converting a basic bark event without DOA."""
        event = BarkEvent(
            timestamp=datetime(2026, 1, 6, 12, 0, 0),
            probability=0.95,
            is_barking=True,
        )

        message = bark_event_to_message(event)

        assert message["type"] == "bark_event"
        assert message["data"]["probability"] == 0.95
        assert message["data"]["is_barking"] is True
        assert "doa" not in message["data"]

    def test_bark_event_with_doa(self) -> None:
        """Test converting bark event with DOA data."""
        event = BarkEvent(
            timestamp=datetime(2026, 1, 6, 12, 0, 0),
            probability=0.95,
            is_barking=True,
            doa_bartlett=135,  # 120-150 range = "right"
            doa_capon=133,
            doa_mem=137,
        )

        message = bark_event_to_message(event)

        assert message["type"] == "bark_event"
        assert "doa" in message["data"]
        assert message["data"]["doa"]["bartlett"] == 135
        assert message["data"]["doa"]["capon"] == 133
        assert message["data"]["doa"]["mem"] == 137
        assert message["data"]["doa"]["direction"] == "right"

    def test_probability_rounding(self) -> None:
        """Test that probability is rounded to 4 decimal places."""
        event = BarkEvent(
            timestamp=datetime(2026, 1, 6, 12, 0, 0),
            probability=0.123456789,
            is_barking=True,
        )

        message = bark_event_to_message(event)

        assert message["data"]["probability"] == 0.1235

    def test_timestamp_format(self) -> None:
        """Test that timestamp is in ISO format."""
        event = BarkEvent(
            timestamp=datetime(2026, 1, 6, 12, 30, 45, 123456),
            probability=0.95,
            is_barking=True,
        )

        message = bark_event_to_message(event)

        assert message["data"]["timestamp"] == "2026-01-06T12:30:45.123456"


class TestBroadcastBarkEvent:
    """Tests for broadcast_bark_event function."""

    @pytest.mark.asyncio
    async def test_broadcast_with_connections(self) -> None:
        """Test broadcasting when there are active connections."""
        manager = ConnectionManager()
        mock_ws = AsyncMock(spec=WebSocket)
        await manager.connect(mock_ws)

        event = BarkEvent(
            timestamp=datetime(2026, 1, 6, 12, 0, 0),
            probability=0.95,
            is_barking=True,
        )

        await broadcast_bark_event(event, manager)

        mock_ws.send_json.assert_called_once()
        call_args = mock_ws.send_json.call_args[0][0]
        assert call_args["type"] == "bark_event"

    @pytest.mark.asyncio
    async def test_broadcast_no_connections(self) -> None:
        """Test broadcasting when no connections exist."""
        manager = ConnectionManager()

        event = BarkEvent(
            timestamp=datetime(2026, 1, 6, 12, 0, 0),
            probability=0.95,
            is_barking=True,
        )

        # Should not raise
        await broadcast_bark_event(event, manager)


# --- WebSocket Endpoint Tests ---


class TestWebSocketBarkEndpoint:
    """Tests for /ws/bark WebSocket endpoint."""

    def test_bark_ws_connection(self, ws_client: TestClient) -> None:
        """Test connecting to bark WebSocket endpoint."""
        with ws_client.websocket_connect("/ws/bark") as websocket:
            # Should receive initial status message
            data = websocket.receive_json()
            assert data["type"] == "status"
            assert data["data"]["running"] is True
            assert data["data"]["total_barks"] == 42

    def test_bark_ws_ping_pong(self, ws_client: TestClient) -> None:
        """Test ping/pong keep-alive."""
        with ws_client.websocket_connect("/ws/bark") as websocket:
            # Receive initial status
            websocket.receive_json()

            # Send ping
            websocket.send_text(json.dumps({"type": "ping"}))

            # Should receive pong
            data = websocket.receive_json()
            assert data["type"] == "pong"

    def test_bark_ws_invalid_json(self, ws_client: TestClient) -> None:
        """Test handling of invalid JSON messages."""
        with ws_client.websocket_connect("/ws/bark") as websocket:
            # Receive initial status
            websocket.receive_json()

            # Send invalid JSON - should not crash
            websocket.send_text("not valid json")

            # Connection should still work - send ping
            websocket.send_text(json.dumps({"type": "ping"}))
            data = websocket.receive_json()
            assert data["type"] == "pong"


class TestWebSocketPipelineEndpoint:
    """Tests for /ws/pipeline WebSocket endpoint."""

    def test_pipeline_ws_connection(self, ws_client: TestClient) -> None:
        """Test connecting to pipeline WebSocket endpoint."""
        with ws_client.websocket_connect("/ws/pipeline") as websocket:
            # Should receive pipeline state message
            data = websocket.receive_json()
            assert data["type"] == "pipeline_state"
            assert "stage" in data["data"]
            assert "vad" in data["data"]
            assert "yamnet" in data["data"]

    def test_pipeline_ws_continuous_updates(self, ws_client: TestClient) -> None:
        """Test that pipeline sends continuous updates."""
        with ws_client.websocket_connect("/ws/pipeline") as websocket:
            # Receive first message
            data1 = websocket.receive_json()
            assert data1["type"] == "pipeline_state"

            # Receive second message
            data2 = websocket.receive_json()
            assert data2["type"] == "pipeline_state"


class TestWebSocketAudioEndpoint:
    """Tests for /ws/audio WebSocket endpoint."""

    def test_audio_ws_connection(self, ws_client: TestClient) -> None:
        """Test connecting to audio WebSocket endpoint."""
        with ws_client.websocket_connect("/ws/audio") as websocket:
            # Should receive initial audio level message
            data = websocket.receive_json()
            assert data["type"] == "audio_level"
            assert "level" in data["data"]
            assert "peak" in data["data"]

    def test_audio_ws_initial_zeros(self, ws_client: TestClient) -> None:
        """Test that audio starts with zero levels."""
        with ws_client.websocket_connect("/ws/audio") as websocket:
            data = websocket.receive_json()
            assert data["data"]["level"] == 0.0
            assert data["data"]["peak"] == 0.0

    def test_audio_ws_continuous_updates(self, ws_client: TestClient) -> None:
        """Test that audio sends continuous updates."""
        with ws_client.websocket_connect("/ws/audio") as websocket:
            # Receive multiple messages
            data1 = websocket.receive_json()
            data2 = websocket.receive_json()

            assert data1["type"] == "audio_level"
            assert data2["type"] == "audio_level"


# --- Integration Tests ---


class TestWebSocketIntegration:
    """Integration tests for WebSocket functionality."""

    def test_multiple_endpoint_connections(self, ws_client: TestClient) -> None:
        """Test connecting to multiple WebSocket endpoints simultaneously."""
        # Note: TestClient doesn't support true parallel connections,
        # but we can test sequential connections work independently

        with ws_client.websocket_connect("/ws/bark") as bark_ws:
            bark_data = bark_ws.receive_json()
            assert bark_data["type"] == "status"

        with ws_client.websocket_connect("/ws/audio") as audio_ws:
            audio_data = audio_ws.receive_json()
            assert audio_data["type"] == "audio_level"

    def test_websocket_graceful_disconnect(self, ws_client: TestClient) -> None:
        """Test that WebSocket handles graceful disconnection."""
        with ws_client.websocket_connect("/ws/bark") as websocket:
            # Receive initial message
            websocket.receive_json()

        # Connection closed - should not raise

    @pytest.mark.asyncio
    async def test_concurrent_broadcasts(self) -> None:
        """Test concurrent broadcasts to multiple connections."""
        manager = ConnectionManager()

        # Create multiple mock connections
        connections = [AsyncMock(spec=WebSocket) for _ in range(5)]
        for conn in connections:
            await manager.connect(conn)

        assert manager.connection_count == 5

        # Broadcast message
        message = {"type": "test", "data": "concurrent"}
        await manager.broadcast(message)

        # All should receive
        for conn in connections:
            conn.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_thread_safety(self) -> None:
        """Test that ConnectionManager is thread-safe."""
        manager = ConnectionManager()

        async def connect_and_disconnect():
            ws = AsyncMock(spec=WebSocket)
            await manager.connect(ws)
            await asyncio.sleep(0.01)  # Small delay
            await manager.disconnect(ws)

        # Run multiple concurrent connect/disconnect operations
        tasks = [connect_and_disconnect() for _ in range(10)]
        await asyncio.gather(*tasks)

        # All connections should be cleaned up
        assert manager.connection_count == 0
