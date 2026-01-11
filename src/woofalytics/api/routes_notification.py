"""API routes for notification status.

Provides endpoints for monitoring the notification system status and statistics.
Authentication is handled by the global AuthMiddleware.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/status")
async def get_notification_status(request: Request) -> dict[str, Any]:
    """Get notification system status and statistics.

    Returns configuration state, delivery statistics, and debouncer metrics.
    Requires authentication (via global middleware).

    Returns:
        Notification system statistics including:
        - enabled: Whether notifications are enabled
        - events_received: Total bark events processed
        - notifications_sent: Successfully sent notifications
        - debouncer: Rate limiting statistics
        - webhook: Delivery statistics
    """
    manager = request.app.state.notification_manager
    return manager.get_stats()
