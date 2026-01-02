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

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import structlog

from woofalytics.config import Settings, load_settings, configure_logging
from woofalytics.detection.model import BarkDetector
from woofalytics.evidence.storage import EvidenceStorage
from woofalytics.api.websocket import broadcast_bark_event

logger = structlog.get_logger(__name__)


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
        version="2.0.0",
        log_level=settings.log_level,
    )

    # Initialize detector
    detector = BarkDetector(settings)

    # Initialize evidence storage (after detector to get audio capture)
    await detector.start()

    evidence = EvidenceStorage(
        config=settings.evidence,
        audio_capture=detector._audio_capture,
        microphone_name=(
            detector._audio_capture.microphone.name
            if detector._audio_capture and detector._audio_capture.microphone
            else "Unknown"
        ),
    )

    # Register callbacks
    detector.add_callback(lambda event: asyncio.create_task(evidence.on_bark_event(event)))
    detector.add_callback(lambda event: asyncio.create_task(broadcast_bark_event(event)))

    # Store in app.state for dependency injection
    app.state.settings = settings
    app.state.detector = detector
    app.state.evidence = evidence

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
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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

    return app


# Dependency injection helpers
def get_settings(request: Request) -> Settings:
    """Get settings from app state."""
    return request.app.state.settings


def get_detector(request: Request) -> BarkDetector:
    """Get bark detector from app state."""
    return request.app.state.detector


def get_evidence(request: Request) -> EvidenceStorage:
    """Get evidence storage from app state."""
    return request.app.state.evidence


# Create the application instance
app = create_app()
