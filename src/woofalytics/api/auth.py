"""API key authentication for Woofalytics.

This module provides simple API key authentication suitable for local network
deployments. Authentication can be disabled by omitting the api_key in config.

Usage:
    REST endpoints: Authorization: Bearer <api_key>
    WebSocket: ?token=<api_key> query parameter

The AuthMiddleware handles REST endpoint authentication automatically.
WebSocket endpoints must call verify_websocket_token() explicitly.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable

import structlog
from fastapi import Request, Response, WebSocket
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)

# Endpoints that bypass authentication (exact match)
PUBLIC_PATHS = frozenset({
    "/api/health",
    "/api/metrics",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
})

# Path prefixes that bypass authentication
PUBLIC_PREFIXES = (
    "/_app/",      # SvelteKit assets
    "/static/",    # Static files
    "/",           # Root SPA route (exact match handled separately)
)

# Module-level configuration
_configured_api_key: str | None = None
_auth_enabled: bool = False


def configure_auth(api_key: str | None) -> None:
    """Configure authentication from settings.

    Args:
        api_key: API key to require, or None to disable authentication.
    """
    global _configured_api_key, _auth_enabled
    _configured_api_key = api_key
    _auth_enabled = api_key is not None and len(api_key) > 0

    if _auth_enabled:
        logger.info("auth_enabled", key_length=len(api_key))
    else:
        logger.warning("auth_disabled", reason="No API key configured")


def is_public_path(path: str) -> bool:
    """Check if a path should bypass authentication.

    Args:
        path: Request path.

    Returns:
        True if the path is public and doesn't need auth.
    """
    # Exact matches
    if path in PUBLIC_PATHS:
        return True

    # Root route (SPA entry point)
    if path == "/":
        return True

    # SPA frontend routes
    if path in ("/dogs", "/fingerprints", "/settings"):
        return True

    # Prefix matches (static assets, etc.)
    for prefix in PUBLIC_PREFIXES:
        if path.startswith(prefix) and prefix != "/":
            return True

    # WebSocket paths (handled separately)
    return path.startswith("/ws/")


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces API key authentication.

    Authentication is bypassed for:
    - Public paths (health, metrics, docs)
    - Static assets
    - WebSocket connections (handled by endpoint)
    - OPTIONS requests (CORS preflight)

    When auth is disabled (no api_key configured), all requests pass through.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with authentication check."""
        # Skip if auth disabled
        if not _auth_enabled:
            return await call_next(request)

        # Skip OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Skip public paths
        path = request.url.path
        if is_public_path(path):
            return await call_next(request)

        # Check Authorization header
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            logger.warning(
                "auth_missing_header",
                path=path,
                method=request.method,
                client_ip=_get_client_ip(request),
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing Authorization header"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Validate Bearer token format
        if not auth_header.startswith("Bearer "):
            logger.warning(
                "auth_invalid_format",
                path=path,
                method=request.method,
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid Authorization format. Use: Bearer <api_key>"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header[7:]  # Remove "Bearer " prefix

        # Constant-time comparison to prevent timing attacks
        if not secrets.compare_digest(token, _configured_api_key):
            logger.warning(
                "auth_invalid_key",
                path=path,
                method=request.method,
                client_ip=_get_client_ip(request),
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid API key"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)


def _get_client_ip(request: Request) -> str:
    """Get client IP, handling proxy headers."""
    x_forwarded = request.headers.get("X-Forwarded-For")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def verify_websocket_token(websocket: WebSocket) -> bool:
    """Verify API key for WebSocket connections.

    WebSocket authentication uses the ?token=<api_key> query parameter.

    Args:
        websocket: WebSocket connection.

    Returns:
        True if authenticated or auth disabled, False otherwise.
    """
    # Auth disabled if no key configured
    if not _auth_enabled:
        return True

    # Get token from query params
    token = websocket.query_params.get("token")

    if not token:
        logger.warning(
            "ws_auth_missing_token",
            path=websocket.url.path,
        )
        return False

    # Constant-time comparison
    if not secrets.compare_digest(token, _configured_api_key):
        logger.warning(
            "ws_auth_invalid_token",
            path=websocket.url.path,
        )
        return False

    return True


def get_auth_status() -> dict:
    """Get current authentication status for debugging.

    Returns:
        Dict with auth enabled status and key length (not the key itself).
    """
    return {
        "enabled": _auth_enabled,
        "key_length": len(_configured_api_key) if _configured_api_key else 0,
    }


def setup_auth(app) -> None:
    """Setup authentication middleware for a FastAPI application.

    Args:
        app: FastAPI application instance.
    """
    app.add_middleware(AuthMiddleware)
    logger.info("auth_middleware_installed")
