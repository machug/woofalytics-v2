"""WebSocket endpoint for real-time bark detection streaming.

This module provides real-time updates to connected clients,
enabling responsive UIs without polling.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketClose
import structlog

from woofalytics.api.auth import verify_websocket_token
from woofalytics.detection.model import BarkEvent
from woofalytics.detection.doa import angle_to_direction

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["websocket"])


class WebSocketManagers:
    """Container for separate WebSocket connection managers by type.

    Each WebSocket endpoint type (bark, pipeline) has its own manager
    to ensure broadcasts only go to the correct client type.
    """

    def __init__(self) -> None:
        self.bark = ConnectionManager("bark")
        self.pipeline = ConnectionManager("pipeline")

    @property
    def total_connections(self) -> int:
        """Total connections across all managers."""
        return (
            self.bark.connection_count +
            self.pipeline.connection_count
        )


class ConnectionManager:
    """Manages WebSocket connections for broadcasting.

    This class handles:
    - Connection lifecycle (connect/disconnect)
    - Broadcasting messages to all connected clients
    - Connection health checking
    """

    def __init__(self, name: str = "default") -> None:
        self.name = name
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info("websocket_connected", manager=self.name, count=len(self.active_connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        removed = False
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
                removed = True
        if removed:
            logger.info("websocket_disconnected", manager=self.name, count=len(self.active_connections))

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
        except Exception as e:
            logger.debug("send_personal_failed", error=str(e), error_type=type(e).__name__)
            await self.disconnect(websocket)
            return False

    @property
    def connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self.active_connections)


def bark_event_to_message(event: BarkEvent, is_circular: bool = False) -> dict[str, Any]:
    """Convert a BarkEvent to a WebSocket message.

    Args:
        event: The bark detection event.
        is_circular: Whether the DOA uses a circular array (UCA) for 360° directions.
    """
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
            "direction": angle_to_direction(event.doa_bartlett, is_circular=is_circular),
        }

    return message


async def broadcast_bark_event(
    event: BarkEvent,
    manager: ConnectionManager,
    is_circular: bool = False,
) -> None:
    """Broadcast a bark event to all connected WebSocket clients.

    Args:
        event: The bark detection event to broadcast.
        manager: The WebSocket connection manager from app.state.
        is_circular: Whether the DOA uses a circular array (UCA) for 360° directions.
    """
    if manager.connection_count > 0:
        message = bark_event_to_message(event, is_circular=is_circular)
        await manager.broadcast(message)


@router.websocket("/ws/bark")
async def websocket_bark_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time bark detection updates.

    Authentication: ?token=<api_key> query parameter (if auth enabled).

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
    # Verify authentication before accepting connection
    if not await verify_websocket_token(websocket):
        await websocket.close(code=4001, reason="Invalid credentials")
        return

    # Use bark-specific manager so broadcasts only go to bark clients
    managers: WebSocketManagers = websocket.app.state.ws_managers
    manager = managers.bark
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


@router.websocket("/ws/pipeline")
async def websocket_pipeline_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time detection pipeline monitoring.

    Authentication: ?token=<api_key> query parameter (if auth enabled).

    Streams live detection pipeline state at ~10Hz for debugging visualization.
    Format:
    {
        "type": "pipeline_state",
        "data": {
            "stage": "bark_detected" | "clap_rejected" | "yamnet_rejected" | "vad_rejected",
            "vad": {"passed": true, "level_db": -25.3, "threshold_db": -40.0},
            "yamnet": {"passed": true, "dog_probability": 0.42, "threshold": 0.05},
            "clap": {"probability": 0.85, "is_barking": true, "top_label": "dog barking loudly", "top_scores": {...}},
            "stats": {"vad_skipped": 100, "yamnet_skipped": 50, "clap_inferences": 200, "total_barks": 5}
        }
    }
    """
    # Verify authentication before accepting connection
    if not await verify_websocket_token(websocket):
        await websocket.close(code=4001, reason="Invalid credentials")
        return

    # Use pipeline-specific manager
    managers: WebSocketManagers = websocket.app.state.ws_managers
    manager = managers.pipeline
    await manager.connect(websocket)

    detector = websocket.app.state.detector

    try:
        while True:
            # Get current pipeline state
            state = detector.get_pipeline_state()

            success = await manager.send_personal(websocket, {
                "type": "pipeline_state",
                "data": state,
            })
            if not success:
                break

            await asyncio.sleep(0.1)  # 10Hz update rate

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.warning("websocket_pipeline_error", error=str(e), error_type=type(e).__name__)
        await manager.disconnect(websocket)

