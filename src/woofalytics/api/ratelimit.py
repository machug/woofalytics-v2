"""Rate limiting for API endpoints.

This module provides configurable rate limiting using SlowAPI middleware
to protect the Raspberry Pi from resource exhaustion through request flooding.

Rate limits are applied globally based on HTTP method:
- GET requests: Higher limits (read operations)
- POST/PUT/DELETE: Lower limits (write operations)
- Evidence downloads: Stricter limits (bandwidth protection)

Note: This module uses middleware-based rate limiting instead of decorators
to avoid issues with PEP 563 (from __future__ import annotations) which
is used throughout this codebase.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

logger = structlog.get_logger(__name__)

# Default rate limits (requests per minute)
DEFAULT_LIMITS = {
    "read": 120,       # 2 requests/second average
    "write": 30,       # More conservative for mutations
    "download": 20,    # Bandwidth protection
    "websocket": 10,   # Connection rate
}

# Configured limits (set via configure_rate_limits)
_configured_limits: dict[str, int] = DEFAULT_LIMITS.copy()
_rate_limiting_enabled: bool = True


def configure_rate_limits(
    read: str | None = None,
    write: str | None = None,
    download: str | None = None,
    websocket: str | None = None,
    metrics: str | None = None,
    enabled: bool = True,
) -> dict[str, int]:
    """Configure rate limits from settings.

    Args:
        read: Rate limit for read operations (e.g., "120/minute").
        write: Rate limit for write operations.
        download: Rate limit for file downloads.
        websocket: Rate limit for WebSocket connections.
        metrics: Rate limit for metrics endpoint (ignored, uses read).
        enabled: Whether rate limiting is enabled.

    Returns:
        Dictionary of configured rate limits.
    """
    global _configured_limits, _rate_limiting_enabled
    _rate_limiting_enabled = enabled

    def parse_limit(limit_str: str | None, default: int) -> int:
        """Parse limit string like '120/minute' to integer."""
        if not limit_str:
            return default
        try:
            return int(limit_str.split("/")[0])
        except (ValueError, IndexError):
            return default

    _configured_limits = {
        "read": parse_limit(read, DEFAULT_LIMITS["read"]),
        "write": parse_limit(write, DEFAULT_LIMITS["write"]),
        "download": parse_limit(download, DEFAULT_LIMITS["download"]),
        "websocket": parse_limit(websocket, DEFAULT_LIMITS["websocket"]),
    }

    logger.info(
        "rate_limits_configured",
        enabled=enabled,
        limits=_configured_limits if enabled else "disabled",
    )

    return _configured_limits


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiting middleware.

    Uses a sliding window approach to track requests per client IP.
    Suitable for single-instance Raspberry Pi deployment.
    """

    def __init__(self, app, window_seconds: int = 60):
        super().__init__(app)
        self.window_seconds = window_seconds
        # Track requests: {client_ip: [(timestamp, path), ...]}
        self._requests: dict[str, list[tuple[float, str]]] = defaultdict(list)

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP, handling proxy headers."""
        x_forwarded = request.headers.get("X-Forwarded-For")
        if x_forwarded:
            return x_forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _get_limit_type(self, request: Request) -> str:
        """Determine limit type based on request."""
        path = request.url.path

        # Evidence file downloads get stricter limits (actual files, not stats/list)
        if "/evidence/" in path and "/file" in path and request.method == "GET":
            return "download"

        # WebSocket connections
        if path.startswith("/ws/"):
            return "websocket"

        # Write operations
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            return "write"

        return "read"

    def _cleanup_old_requests(self, client_ip: str, now: float) -> None:
        """Remove requests older than the window."""
        cutoff = now - self.window_seconds
        self._requests[client_ip] = [
            (ts, path) for ts, path in self._requests[client_ip]
            if ts > cutoff
        ]

    def _count_requests(self, client_ip: str, limit_type: str) -> int:
        """Count requests in the current window for a limit type."""
        return len(self._requests[client_ip])

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting."""
        # Skip if disabled
        if not _rate_limiting_enabled:
            return await call_next(request)

        # Skip OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Skip static files
        path = request.url.path
        if path.startswith(("/_app/", "/static/")):
            return await call_next(request)

        client_ip = self._get_client_ip(request)

        # Skip localhost - don't rate limit the local frontend
        if client_ip in ("127.0.0.1", "::1", "localhost"):
            return await call_next(request)
        limit_type = self._get_limit_type(request)
        limit = _configured_limits.get(limit_type, 120)
        now = time.time()

        # Cleanup and count
        self._cleanup_old_requests(client_ip, now)
        request_count = self._count_requests(client_ip, limit_type)

        # Check if over limit
        if request_count >= limit:
            logger.warning(
                "rate_limit_exceeded",
                client_ip=client_ip,
                path=path,
                limit=limit,
                limit_type=limit_type,
                request_count=request_count,
            )
            return Response(
                content='{"detail": "Rate limit exceeded. Please slow down."}',
                status_code=429,
                media_type="application/json",
                headers={
                    "Retry-After": str(self.window_seconds),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(now + self.window_seconds)),
                },
            )

        # Track this request
        self._requests[client_ip].append((now, path))

        # Process request and add headers
        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - request_count - 1))
        response.headers["X-RateLimit-Reset"] = str(int(now + self.window_seconds))

        return response


# Legacy limiter for compatibility (used by decorators)
# Note: Decorator-based limiting doesn't work well with PEP 563 annotations
limiter = None  # Disabled to avoid issues


def setup_rate_limiting(app) -> None:
    """Setup rate limiting middleware for a FastAPI application.

    Args:
        app: FastAPI application instance.
    """
    app.add_middleware(RateLimitMiddleware)
    logger.info("rate_limit_middleware_installed")
