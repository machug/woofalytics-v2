"""Configuration management using Pydantic v2 settings.

This module implements proper Pydantic v2 patterns:
- Only the root Settings class inherits from BaseSettings
- Nested configs use BaseModel to avoid env var conflicts
- Environment variables use WOOFALYTICS__ prefix with __ delimiter
- YAML config file support with env var override

Examples:
    Load with defaults:
        >>> settings = load_settings()

    Load from YAML:
        >>> settings = load_settings(Path("config.yaml"))

    Override via environment:
        $ export WOOFALYTICS__MODEL__THRESHOLD=0.9
        $ export WOOFALYTICS__WEBHOOK__IFTTT_KEY=your_key
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AudioConfig(BaseModel):
    """Audio capture configuration.

    Note: This is a BaseModel, not BaseSettings, to avoid
    independent env var loading for nested configs.
    """

    device_name: str | None = Field(
        default=None,
        description="Microphone device name filter. None = auto-detect any 2+ channel mic.",
    )
    sample_rate: int = Field(
        default=44100,
        ge=8000,
        le=192000,
        description="Recording sample rate in Hz.",
    )
    channels: int = Field(
        default=2,
        ge=1,
        le=8,
        description="Number of audio channels.",
    )
    chunk_size: int = Field(
        default=441,
        ge=64,
        le=4096,
        description="Audio buffer chunk size in samples.",
    )
    volume_percent: int = Field(
        default=75,
        ge=0,
        le=100,
        description="Microphone capture volume percentage.",
    )


class ModelConfig(BaseModel):
    """ML model configuration."""

    # CLAP zero-shot detection (recommended)
    use_clap: bool = Field(
        default=True,
        description="Use CLAP zero-shot model instead of legacy MLP. Recommended for better speech rejection.",
    )
    clap_model: str = Field(
        default="laion/clap-htsat-unfused",
        description="Hugging Face model ID for CLAP.",
    )
    clap_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="CLAP bark detection threshold.",
    )
    clap_bird_veto_threshold: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="Bird sound threshold for vetoing bark detections. Lower = more aggressive bird rejection.",
    )
    clap_min_harmonic_ratio: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Minimum harmonic ratio for bark detection. Lower = accept noisier barks. Set to 0 to disable.",
    )
    clap_device: str = Field(
        default="cpu",
        description="Device for CLAP inference ('cpu' or 'cuda').",
    )

    # VAD gate for fast rejection
    vad_enabled: bool = Field(
        default=True,
        description="Enable VAD gate to skip CLAP inference on silence.",
    )
    vad_threshold_db: float = Field(
        default=-40.0,
        ge=-80.0,
        le=0.0,
        description="VAD energy threshold in dBFS. Audio below this is skipped.",
    )

    # YAMNet pre-filter settings
    yamnet_enabled: bool = Field(
        default=True,
        description="Enable YAMNet pre-filter to skip CLAP on non-dog audio.",
    )
    yamnet_threshold: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="YAMNet dog probability threshold for running CLAP.",
    )
    yamnet_fallback_to_clap: bool = Field(
        default=True,
        description="Fall back to CLAP-only if YAMNet fails to load.",
    )

    # Legacy MLP model settings (used when use_clap=False)
    path: Path = Field(
        default=Path("./models/traced_model.pt"),
        description="Path to TorchScript traced model file (legacy).",
    )
    target_sample_rate: int = Field(
        default=16000,
        description="Sample rate expected by the model (will resample if different).",
    )
    threshold: float = Field(
        default=0.88,
        ge=0.0,
        le=1.0,
        description="Bark detection probability threshold (legacy MLP).",
    )
    window_ms: int = Field(
        default=6,
        ge=1,
        le=100,
        description="Inference window size in milliseconds.",
    )
    overlap_ms: int = Field(
        default=3,
        ge=0,
        le=50,
        description="Inference window overlap in milliseconds.",
    )


class DOAConfig(BaseModel):
    """Direction of Arrival estimation configuration."""

    enabled: bool = Field(
        default=True,
        description="Enable direction of arrival estimation.",
    )
    element_spacing: float = Field(
        default=0.1,
        ge=0.01,
        le=1.0,
        description="Inter-element spacing in wavelengths (lambda).",
    )
    num_elements: int = Field(
        default=2,
        ge=2,
        le=8,
        description="Number of microphone elements in the array.",
    )
    angle_min: int = Field(
        default=0,
        ge=0,
        le=180,
        description="Minimum scanning angle in degrees.",
    )
    angle_max: int = Field(
        default=180,
        ge=0,
        le=360,
        description="Maximum scanning angle in degrees.",
    )
    method: str = Field(
        default="bartlett",
        description="DOA algorithm to use: 'bartlett' (fast), 'capon' (high-res), or 'mem' (best for close sources).",
    )


class WebhookConfig(BaseModel):
    """Webhook/IFTTT notification configuration."""

    enabled: bool = Field(
        default=False,
        description="Enable webhook notifications on bark detection.",
    )
    ifttt_event: str = Field(
        default="woof",
        description="IFTTT Maker Webhooks event name.",
    )
    ifttt_key: str = Field(
        default="",
        description="IFTTT Maker Webhooks API key (use env var WOOFALYTICS__WEBHOOK__IFTTT_KEY).",
    )
    custom_url: str | None = Field(
        default=None,
        description="Custom webhook URL (alternative to IFTTT).",
    )


class EvidenceConfig(BaseModel):
    """Evidence recording configuration for council complaints."""

    directory: Path = Field(
        default=Path("./evidence"),
        description="Directory to store evidence recordings.",
    )
    past_context_seconds: int = Field(
        default=15,
        ge=1,
        le=60,
        description="Seconds of audio to keep before bark detection.",
    )
    future_context_seconds: int = Field(
        default=15,
        ge=1,
        le=60,
        description="Seconds of audio to record after bark detection.",
    )
    include_metadata: bool = Field(
        default=True,
        description="Generate JSON sidecar with timestamp, DOA, and probability.",
    )
    auto_record: bool = Field(
        default=True,
        description="Automatically record when bark is detected.",
    )


class RateLimitConfig(BaseModel):
    """Rate limiting configuration to prevent DoS attacks."""

    enabled: bool = Field(
        default=True,
        description="Enable rate limiting on API endpoints.",
    )
    read_limit: str = Field(
        default="120/minute",
        description="Rate limit for read operations (GET requests).",
    )
    write_limit: str = Field(
        default="30/minute",
        description="Rate limit for write operations (POST/PUT/DELETE).",
    )
    download_limit: str = Field(
        default="20/minute",
        description="Rate limit for evidence file downloads.",
    )
    websocket_limit: str = Field(
        default="10/minute",
        description="Rate limit for new WebSocket connections.",
    )


class ServerConfig(BaseModel):
    """Web server configuration."""

    host: str = Field(
        default="127.0.0.1",
        description="Host address to bind to. Defaults to localhost for security.",
    )
    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Port number to listen on.",
    )
    enable_websocket: bool = Field(
        default=True,
        description="Enable WebSocket endpoint for real-time updates.",
    )
    cors_origins: list[str] | None = Field(
        default=None,
        description="Allowed CORS origins. Defaults to localhost only if not set.",
    )
    rate_limit: RateLimitConfig = Field(
        default_factory=RateLimitConfig,
        description="Rate limiting configuration.",
    )
    api_key: str | None = Field(
        default=None,
        description=(
            "API key for authentication. If not set, authentication is disabled. "
            "Generate with: python -c 'import secrets; print(secrets.token_hex(16))'"
        ),
    )


class Settings(BaseSettings):
    """Root application settings.

    This is the only class that inherits from BaseSettings.
    Configuration can be loaded from:
    1. Default values
    2. YAML config file
    3. Environment variables (highest priority)

    Environment variable format: WOOFALYTICS__SECTION__KEY
    Example: WOOFALYTICS__MODEL__THRESHOLD=0.9
    """

    model_config = SettingsConfigDict(
        env_prefix="WOOFALYTICS__",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Nested configuration sections
    audio: AudioConfig = Field(default_factory=AudioConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    doa: DOAConfig = Field(default_factory=DOAConfig)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    evidence: EvidenceConfig = Field(default_factory=EvidenceConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)

    # Top-level settings
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Logging verbosity level.",
    )
    log_format: Literal["console", "json"] = Field(
        default="console",
        description="Log output format (console for dev, json for production).",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode with additional diagnostics.",
    )


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings from YAML file and/or environment variables.

    Args:
        config_path: Optional path to YAML configuration file.
                    Environment variables always override YAML values.

    Returns:
        Fully populated Settings instance.

    Examples:
        >>> settings = load_settings()  # Defaults + env vars
        >>> settings = load_settings(Path("config.yaml"))  # YAML + env vars
    """
    import yaml

    yaml_config: dict = {}

    if config_path and config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            yaml_config = yaml.safe_load(f) or {}

    # Merge YAML config with env vars (env vars take priority via BaseSettings)
    return Settings(**yaml_config)


def configure_logging(
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"],
    log_format: Literal["console", "json"],
) -> None:
    """Configure structlog with the specified level and format.

    Args:
        log_level: Logging verbosity level.
        log_format: Output format - 'console' for dev, 'json' for production.
    """
    import logging

    import structlog

    # Set stdlib logging level
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level),
    )

    # Common processors
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if log_format == "json":
        # JSON format for production/log aggregation
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, log_level)
            ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        # Console format for development
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, log_level)
            ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )


# Default config file location
DEFAULT_CONFIG_PATH = Path("config.yaml")
