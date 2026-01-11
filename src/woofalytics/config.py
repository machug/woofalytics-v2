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

import ipaddress
from datetime import datetime, time
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import structlog
from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger(__name__)


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


class NotificationConfig(BaseModel):
    """Top-level notification system settings."""

    enabled: bool = Field(
        default=False,
        description="Enable notification system.",
    )


class WebhookConfig(BaseModel):
    """Webhook notification configuration with security hardening."""

    enabled: bool = Field(
        default=False,
        description="Enable webhook notifications on bark detection.",
    )

    # IFTTT Maker Webhooks
    ifttt_event: str = Field(
        default="woof",
        description="IFTTT Maker Webhooks event name.",
    )
    ifttt_key: SecretStr = Field(
        default=SecretStr(""),
        description="IFTTT Maker Webhooks API key (use env var WOOFALYTICS__WEBHOOK__IFTTT_KEY).",
    )

    # Custom webhook
    custom_url: str | None = Field(
        default=None,
        description="Custom webhook URL (must be HTTPS, no private IPs).",
    )
    custom_headers: dict[str, str] = Field(
        default_factory=dict,
        description="Custom headers for webhook requests.",
    )
    custom_auth_token: SecretStr = Field(
        default=SecretStr(""),
        description="Bearer token for custom webhook (optional).",
    )

    # Delivery settings
    timeout_seconds: float = Field(
        default=10.0,
        ge=1.0,
        le=30.0,
        description="HTTP request timeout.",
    )
    retry_count: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Number of retry attempts on failure.",
    )

    # Debouncing
    debounce_seconds: int = Field(
        default=300,  # 5 minutes
        ge=60,
        le=3600,
        description="Minimum seconds between notifications for same dog.",
    )

    @field_validator("custom_url")
    @classmethod
    def validate_custom_url(cls, v: str | None) -> str | None:
        """Validate custom URL for SSRF protection."""
        if v is None:
            return None

        parsed = urlparse(v)

        # Must be HTTPS
        if parsed.scheme != "https":
            raise ValueError("Custom webhook URL must use HTTPS")

        # Check for private/loopback IPs
        hostname = parsed.hostname
        if hostname:
            try:
                # Try to parse as IP address
                ip = ipaddress.ip_address(hostname)
            except ValueError:
                # Not an IP address, hostname is fine (checked below for blocked names)
                pass
            else:
                # Valid IP - check if private/internal
                if ip.is_private or ip.is_loopback or ip.is_reserved:
                    raise ValueError("Custom webhook URL cannot point to private/internal IPs")

        # Block common internal hostnames
        blocked_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "metadata.google", "169.254.169.254"}
        if hostname and hostname.lower() in blocked_hosts:
            raise ValueError("Custom webhook URL cannot point to internal hosts")

        return v


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


class QuietHoursConfig(BaseModel):
    """Quiet hours configuration for scheduled sensitivity adjustment.

    During quiet hours (e.g., overnight), detection threshold can be raised
    to reduce false positives, and notifications can be suppressed.
    Evidence is always recorded regardless of quiet hours.

    Time ranges can cross midnight (e.g., 22:00-06:00).
    """

    enabled: bool = Field(
        default=False,
        description="Enable quiet hours mode.",
    )
    start: time = Field(
        default=time(22, 0),  # 10 PM
        description="Start time for quiet hours (HH:MM format in config).",
    )
    end: time = Field(
        default=time(6, 0),  # 6 AM
        description="End time for quiet hours (HH:MM format in config).",
    )
    threshold: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Higher detection threshold during quiet hours (reduces sensitivity).",
    )
    notifications: bool = Field(
        default=False,
        description="Whether to send notifications during quiet hours.",
    )
    timezone: str = Field(
        default="UTC",
        description="IANA timezone for evaluating quiet hours (e.g., 'Australia/Sydney').",
    )

    @field_validator("start", "end", mode="before")
    @classmethod
    def parse_time_string(cls, v: str | time) -> time:
        """Parse HH:MM string to time object."""
        if isinstance(v, time):
            return v
        try:
            return datetime.strptime(v, "%H:%M").time()
        except ValueError as e:
            raise ValueError(f"Invalid time format: {v}. Use HH:MM (e.g., '22:00')") from e

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Validate timezone is a valid IANA timezone."""
        try:
            ZoneInfo(v)
        except Exception as e:
            raise ValueError(f"Invalid timezone: {v}. Use IANA timezone names like 'Australia/Sydney'") from e
        return v

    def is_active(self) -> bool:
        """Check if current time is within quiet hours.

        Handles time ranges that cross midnight (e.g., 22:00-06:00).
        Returns False on any error (fail safe - don't suppress notifications).
        """
        if not self.enabled:
            return False

        try:
            now = datetime.now(ZoneInfo(self.timezone)).time()
            if self.start <= self.end:
                # Same day range (e.g., 09:00-17:00)
                return self.start <= now < self.end
            else:
                # Crosses midnight (e.g., 22:00-06:00)
                return now >= self.start or now < self.end
        except Exception as e:
            logger.warning("quiet_hours_check_failed", error=str(e))
            return False  # Fail safe: not in quiet hours

    def get_threshold(self, default: float) -> float:
        """Return quiet hours threshold if active, else default threshold."""
        return self.threshold if self.is_active() else default


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
    notification: NotificationConfig = Field(default_factory=NotificationConfig)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    evidence: EvidenceConfig = Field(default_factory=EvidenceConfig)
    quiet_hours: QuietHoursConfig = Field(default_factory=QuietHoursConfig)
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
