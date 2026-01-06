"""FastAPI application for Woofalytics.

This module provides the main web application with:
- REST API for bark detection status and evidence retrieval
- WebSocket for real-time bark probability streaming
- Static file serving for the web UI
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

from woofalytics import __version__
from woofalytics.config import Settings, load_settings, configure_logging
from woofalytics.detection.model import BarkDetector, BarkEvent
from woofalytics.evidence.storage import EvidenceStorage
from woofalytics.api.websocket import broadcast_bark_event, ConnectionManager
from woofalytics.api.ratelimit import setup_rate_limiting, configure_rate_limits
from woofalytics.fingerprint.storage import FingerprintStore
from woofalytics.fingerprint.matcher import FingerprintMatcher

logger = structlog.get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        # Prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # XSS protection (legacy, but still useful for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Don't expose server version
        response.headers["Server"] = "Woofalytics"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan - startup and shutdown.

    This manages the lifecycle of:
    - Configuration loading
    - Bark detector with audio capture
    - Evidence storage
    - Background tasks
    """
    # Load configuration
    config_path = Path("config.yaml")
    settings = load_settings(config_path if config_path.exists() else None)

    # Configure logging
    configure_logging(settings.log_level, settings.log_format)

    logger.info(
        "woofalytics_starting",
        version=__version__,
        log_level=settings.log_level,
    )

    # Configure rate limiting from settings
    rate_limit_config = settings.server.rate_limit
    configure_rate_limits(
        read=rate_limit_config.read_limit,
        write=rate_limit_config.write_limit,
        download=rate_limit_config.download_limit,
        websocket=rate_limit_config.websocket_limit,
        enabled=rate_limit_config.enabled,
    )

    # Initialize detector
    detector = BarkDetector(settings)

    # Initialize evidence storage (after detector to get audio capture)
    await detector.start()

    evidence = EvidenceStorage(
        config=settings.evidence,
        audio_capture=detector.audio_capture,
        microphone_name=(
            detector.audio_capture.microphone.name
            if detector.audio_capture and detector.audio_capture.microphone
            else "Unknown"
        ),
    )

    # Create WebSocket connection manager
    ws_manager = ConnectionManager()

    # Initialize fingerprint system for dog identification
    fingerprint_db_path = settings.evidence.directory / "fingerprints.db"
    fingerprint_store = FingerprintStore(fingerprint_db_path)
    fingerprint_matcher = FingerprintMatcher(
        detector=detector._clap_detector,
        store=fingerprint_store,
        threshold=0.7,  # Similarity threshold for matching
    )
    logger.info("fingerprint_system_initialized", db_path=str(fingerprint_db_path))

    # Link evidence files to fingerprints when saved
    def on_evidence_saved(filename: str, first_bark: datetime, last_bark: datetime) -> None:
        """Link saved evidence file to fingerprints created during that time."""
        fingerprint_store.link_evidence_to_fingerprints(filename, first_bark, last_bark)

    evidence.add_on_saved_callback(on_evidence_saved)

    # Fingerprint callback - process detected barks for dog identification
    def on_bark_for_fingerprint(event: BarkEvent) -> None:
        if event.is_barking and event.audio is not None:
            try:
                fingerprint, matches = fingerprint_matcher.process_bark(
                    audio=event.audio,
                    sample_rate=event.sample_rate,
                    detection_prob=event.probability,
                    doa=event.doa_bartlett,
                )
                if matches:
                    logger.info(
                        "bark_identified",
                        dog_name=matches[0].dog_name,
                        confidence=f"{matches[0].confidence:.3f}",
                    )
            except Exception as e:
                logger.warning("fingerprint_processing_error", error=str(e))

    # Register callbacks
    detector.add_callback(lambda event: asyncio.create_task(evidence.on_bark_event(event)))
    detector.add_callback(lambda event: asyncio.create_task(broadcast_bark_event(event, ws_manager)))
    detector.add_callback(on_bark_for_fingerprint)

    # Store in app.state for dependency injection
    app.state.settings = settings
    app.state.detector = detector
    app.state.evidence = evidence
    app.state.ws_manager = ws_manager
    app.state.fingerprint_store = fingerprint_store
    app.state.fingerprint_matcher = fingerprint_matcher

    # Start background task for evidence saving
    async def evidence_saver() -> None:
        while True:
            await asyncio.sleep(1.0)
            await evidence.check_and_save()

    evidence_task = asyncio.create_task(evidence_saver())

    logger.info("woofalytics_started")

    yield

    # Shutdown
    logger.info("woofalytics_stopping")

    evidence_task.cancel()
    try:
        await evidence_task
    except asyncio.CancelledError:
        pass

    await detector.stop()

    logger.info("woofalytics_stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(
        title="Woofalytics",
        description="AI-powered dog bark detection with evidence collection",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # CORS middleware - restrict to localhost by default for security
    # Note: CORS origins are configured at startup via lifespan, but we need
    # sensible defaults here. For custom origins, set WOOFALYTICS__SERVER__CORS_ORIGINS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
        allow_credentials=False,  # No auth system, no credentials needed
        allow_methods=["GET", "POST", "OPTIONS", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Accept"],
    )

    # Security headers middleware
    app.add_middleware(SecurityHeadersMiddleware)

    # Rate limiting setup
    setup_rate_limiting(app)

    # Import and include API routes
    from woofalytics.api.routes import router as api_router
    from woofalytics.api.websocket import router as ws_router

    app.include_router(api_router, prefix="/api")
    app.include_router(ws_router)

    # Path to project root (3 levels up from app.py)
    project_root = Path(__file__).parent.parent.parent

    # SvelteKit build output (production frontend)
    frontend_build_path = project_root / "frontend" / "build"

    # Legacy static files (evidence audio files served from here)
    static_path = project_root / "static"

    # Mount evidence/audio static files if they exist
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=static_path), name="static")

    # Mount SvelteKit assets (_app directory with JS/CSS)
    if frontend_build_path.exists():
        app.mount(
            "/_app",
            StaticFiles(directory=frontend_build_path / "_app"),
            name="frontend_assets",
        )

    # SPA catch-all: serve index.html for all non-API, non-static routes
    @app.get("/", include_in_schema=False, response_model=None)
    @app.get("/dogs", include_in_schema=False, response_model=None)
    @app.get("/fingerprints", include_in_schema=False, response_model=None)
    @app.get("/settings", include_in_schema=False, response_model=None)
    async def spa_routes():
        """Serve SvelteKit SPA for all frontend routes."""
        index_path = frontend_build_path / "index.html"
        if index_path.exists():
            return FileResponse(index_path, media_type="text/html")
        # Fallback when frontend not built
        return {"message": "Woofalytics API running", "docs": "/api/docs"}

    # Serve robots.txt from frontend build
    @app.get("/robots.txt", include_in_schema=False, response_model=None)
    async def robots():
        robots_path = frontend_build_path / "robots.txt"
        if robots_path.exists():
            return FileResponse(robots_path, media_type="text/plain")
        return Response(content="User-agent: *\nDisallow: /api/", media_type="text/plain")

    return app


# Create the application instance
app = create_app()
