"""WebSocket endpoint for real-time bark detection streaming.

This module provides real-time updates to connected clients,
enabling responsive UIs without polling.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import structlog

from woofalytics.detection.model import BarkEvent
from woofalytics.detection.doa import angle_to_direction

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manages WebSocket connections for broadcasting.

    This class handles:
    - Connection lifecycle (connect/disconnect)
    - Broadcasting messages to all connected clients
    - Connection health checking
    """

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info("websocket_connected", total=len(self.active_connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        removed = False
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
                removed = True
        if removed:
            logger.info("websocket_disconnected", total=len(self.active_connections))

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast a message to all connected clients.

        Handles disconnected clients gracefully by removing them.
        """
        async with self._lock:
            connections = self.active_connections.copy()

        disconnected = []

        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        # Clean up disconnected clients
        if disconnected:
            async with self._lock:
                for conn in disconnected:
                    if conn in self.active_connections:
                        self.active_connections.remove(conn)

    async def send_personal(
        self,
        websocket: WebSocket,
        message: dict[str, Any],
    ) -> bool:
        """Send a message to a specific client.

        Returns True if sent successfully, False if failed.
        """
        try:
            await websocket.send_json(message)
            return True
        except Exception:
            await self.disconnect(websocket)
            return False

    @property
    def connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self.active_connections)


def bark_event_to_message(event: BarkEvent) -> dict[str, Any]:
    """Convert a BarkEvent to a WebSocket message."""
    message: dict[str, Any] = {
        "type": "bark_event",
        "data": {
            "timestamp": event.timestamp.isoformat(),
            "probability": round(event.probability, 4),
            "is_barking": event.is_barking,
        },
    }

    # Add DOA data if available
    if event.doa_bartlett is not None:
        message["data"]["doa"] = {
            "bartlett": event.doa_bartlett,
            "capon": event.doa_capon,
            "mem": event.doa_mem,
            "direction": angle_to_direction(event.doa_bartlett),
        }

    return message


async def broadcast_bark_event(event: BarkEvent, manager: ConnectionManager) -> None:
    """Broadcast a bark event to all connected WebSocket clients.

    Args:
        event: The bark detection event to broadcast.
        manager: The WebSocket connection manager from app.state.
    """
    if manager.connection_count > 0:
        message = bark_event_to_message(event)
        await manager.broadcast(message)


@router.websocket("/ws/bark")
async def websocket_bark_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time bark detection updates.

    Clients receive JSON messages with the format:
    {
        "type": "bark_event",
        "data": {
            "timestamp": "2024-01-15T14:32:45.123456",
            "probability": 0.95,
            "is_barking": true,
            "doa": {
                "bartlett": 135,
                "capon": 132,
                "mem": 138,
                "direction": "right"
            }
        }
    }
    """
    manager = websocket.app.state.ws_manager
    await manager.connect(websocket)

    detector = websocket.app.state.detector

    # Send initial status
    status = detector.get_status()
    success = await manager.send_personal(websocket, {
        "type": "status",
        "data": {
            "running": status["running"],
            "uptime_seconds": status["uptime_seconds"],
            "total_barks": status["total_barks"],
            "microphone": status["microphone"],
        },
    })
    if not success:
        return  # Client disconnected immediately

    try:
        while True:
            # Keep connection alive and handle any incoming messages
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0,
                )
                # Handle client messages (ping, commands, etc.)
                try:
                    message = json.loads(data)
                    if message.get("type") == "ping":
                        if not await manager.send_personal(websocket, {"type": "pong"}):
                            break
                except json.JSONDecodeError:
                    pass

            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                if not await manager.send_personal(websocket, {"type": "ping"}):
                    break

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.warning("websocket_error", error=str(e))
        await manager.disconnect(websocket)


@router.websocket("/ws/audio")
async def websocket_audio_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time audio level monitoring.

    Sends audio level updates at ~10Hz for VU meter visualization.
    Format: {"type": "audio_level", "data": {"level": 0.75, "peak": 0.92}}
    """
    manager = websocket.app.state.ws_manager
    await manager.connect(websocket)

    detector = websocket.app.state.detector

    # Send initial message to confirm connection
    success = await manager.send_personal(websocket, {
        "type": "audio_level",
        "data": {"level": 0.0, "peak": 0.0},
    })
    if not success:
        return  # Client disconnected immediately

    try:
        while True:
            # Calculate current audio level from recent frames
            if detector.audio_capture:
                frames = detector.audio_capture.get_recent_frames(count=2)
                if frames:
                    import numpy as np

                    # Combine frame data
                    audio_data = b"".join(f.data for f in frames)
                    audio_array = np.frombuffer(audio_data, dtype=np.int16)

                    # Calculate RMS level
                    rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
                    level = min(1.0, rms / 32768.0 * 10)  # Normalize to 0-1

                    # Calculate peak
                    peak = min(1.0, np.abs(audio_array).max() / 32768.0)

                    success = await manager.send_personal(websocket, {
                        "type": "audio_level",
                        "data": {
                            "level": round(level, 3),
                            "peak": round(peak, 3),
                        },
                    })
                    if not success:
                        break  # Client disconnected

            await asyncio.sleep(0.1)  # 10Hz update rate

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.warning("websocket_audio_error", error=str(e))
        await manager.disconnect(websocket)
