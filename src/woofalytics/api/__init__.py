"""FastAPI routes and WebSocket handlers."""

from woofalytics.api.routes import router
from woofalytics.api.websocket import ConnectionManager

__all__ = ["router", "ConnectionManager"]
