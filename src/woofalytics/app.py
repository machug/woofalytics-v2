"""FastAPI application for Woofalytics.

This module provides the main web application with:
- REST API for bark detection status and evidence retrieval
- WebSocket for real-time bark probability streaming
- Static file serving for the web UI
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
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
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )

    # Security headers middleware
    app.add_middleware(SecurityHeadersMiddleware)

    # Import and include API routes
    from woofalytics.api.routes import router as api_router
    from woofalytics.api.websocket import router as ws_router

    app.include_router(api_router, prefix="/api")
    app.include_router(ws_router)

    # Static files - path is relative to src/woofalytics/app.py
    # Go up 3 levels: app.py -> woofalytics -> src -> project_root
    static_path = Path(__file__).parent.parent.parent / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=static_path), name="static")

    # Root serves index.html
    @app.get("/", include_in_schema=False, response_model=None)
    async def root():
        index_path = static_path / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        # Fallback when static files not found
        return {"message": "Woofalytics API running", "docs": "/api/docs"}

    # Dogs admin page
    @app.get("/dogs.html", include_in_schema=False, response_model=None)
    async def dogs_page():
        dogs_path = static_path / "dogs.html"
        if dogs_path.exists():
            return FileResponse(dogs_path)
        return {"error": "Dogs page not found"}

    return app


# Create the application instance
app = create_app()
