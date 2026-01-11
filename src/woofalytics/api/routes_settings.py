"""Settings API routes.

Provides endpoints for viewing and updating application settings.
Settings are persisted to config.yaml and require a restart to take effect.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import structlog
import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from woofalytics.config import Settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

CONFIG_PATH = Path("config.yaml")


# --- Schemas ---


class ModelSettingsSchema(BaseModel):
    """Model/detection settings (editable subset)."""

    clap_threshold: float = Field(
        ge=0.0, le=1.0, description="CLAP bark detection threshold"
    )
    clap_bird_veto_threshold: float = Field(
        ge=0.0, le=1.0, description="Bird sound veto threshold"
    )
    clap_min_harmonic_ratio: float = Field(
        ge=0.0, le=1.0, description="Minimum harmonic ratio (lower = accept noisier barks)"
    )
    vad_enabled: bool = Field(description="Enable VAD silence gate")
    vad_threshold_db: float = Field(
        ge=-80.0, le=0.0, description="VAD energy threshold in dBFS"
    )
    yamnet_enabled: bool = Field(description="Enable YAMNet pre-filter")
    yamnet_threshold: float = Field(
        ge=0.0, le=1.0, description="YAMNet dog probability threshold"
    )


class EvidenceSettingsSchema(BaseModel):
    """Evidence recording settings."""

    past_context_seconds: int = Field(
        ge=1, le=60, description="Seconds before bark trigger"
    )
    future_context_seconds: int = Field(
        ge=1, le=60, description="Seconds after last bark"
    )
    auto_record: bool = Field(description="Automatically record on bark detection")


class WebhookSettingsSchema(BaseModel):
    """Webhook notification settings."""

    enabled: bool = Field(description="Enable webhook notifications")
    ifttt_event: str = Field(description="IFTTT event name")
    ifttt_key: str = Field(default="", description="IFTTT API key (write-only)")


class QuietHoursSettingsSchema(BaseModel):
    """Quiet hours / scheduled sensitivity settings."""

    enabled: bool = Field(description="Enable quiet hours mode")
    start: str = Field(description="Start time (HH:MM format, e.g., '22:00')")
    end: str = Field(description="End time (HH:MM format, e.g., '06:00')")
    threshold: float = Field(
        ge=0.0, le=1.0, description="Detection threshold during quiet hours (higher = less sensitive)"
    )
    notifications: bool = Field(description="Send notifications during quiet hours")
    timezone: str = Field(description="IANA timezone (e.g., 'Australia/Sydney', 'America/New_York')")


class AllSettingsSchema(BaseModel):
    """Complete editable settings."""

    model: ModelSettingsSchema
    evidence: EvidenceSettingsSchema
    webhook: WebhookSettingsSchema
    quiet_hours: QuietHoursSettingsSchema


class SettingsUpdateSchema(BaseModel):
    """Settings update request (all fields optional)."""

    model: ModelSettingsSchema | None = None
    evidence: EvidenceSettingsSchema | None = None
    webhook: WebhookSettingsSchema | None = None
    quiet_hours: QuietHoursSettingsSchema | None = None


class SettingsResponseSchema(BaseModel):
    """Settings response with restart info."""

    settings: AllSettingsSchema
    config_path: str
    restart_required: bool = False
    message: str | None = None


# --- Helpers ---


def get_settings(request: Request) -> Settings:
    """Get settings from app state."""
    return request.app.state.settings


def _settings_to_schema(settings: Settings) -> AllSettingsSchema:
    """Convert Settings to API schema."""
    return AllSettingsSchema(
        model=ModelSettingsSchema(
            clap_threshold=settings.model.clap_threshold,
            clap_bird_veto_threshold=settings.model.clap_bird_veto_threshold,
            clap_min_harmonic_ratio=settings.model.clap_min_harmonic_ratio,
            vad_enabled=settings.model.vad_enabled,
            vad_threshold_db=settings.model.vad_threshold_db,
            yamnet_enabled=settings.model.yamnet_enabled,
            yamnet_threshold=settings.model.yamnet_threshold,
        ),
        evidence=EvidenceSettingsSchema(
            past_context_seconds=settings.evidence.past_context_seconds,
            future_context_seconds=settings.evidence.future_context_seconds,
            auto_record=settings.evidence.auto_record,
        ),
        webhook=WebhookSettingsSchema(
            enabled=settings.webhook.enabled,
            ifttt_event=settings.webhook.ifttt_event,
            # Don't expose the actual key, just show if it's set
            ifttt_key="••••••••" if settings.webhook.ifttt_key else "",
        ),
        quiet_hours=QuietHoursSettingsSchema(
            enabled=settings.quiet_hours.enabled,
            start=settings.quiet_hours.start.strftime("%H:%M"),
            end=settings.quiet_hours.end.strftime("%H:%M"),
            threshold=settings.quiet_hours.threshold,
            notifications=settings.quiet_hours.notifications,
            timezone=settings.quiet_hours.timezone,
        ),
    )


def _load_config_yaml() -> dict:
    """Load existing config.yaml or return empty dict."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_config_yaml(config: dict) -> None:
    """Save config to config.yaml with comments preserved where possible."""
    # Read existing file to preserve comments
    header = """# Woofalytics Configuration
# -------------------------
# This file is managed by the Woofalytics settings UI.
# Environment variables take precedence over this file.
# Environment variables use the prefix WOOFALYTICS__ with __ as delimiter.
# Example: WOOFALYTICS__MODEL__CLAP_THRESHOLD=0.7

"""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(header)
        yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)


# --- Endpoints ---


@router.get("", response_model=SettingsResponseSchema)
async def get_all_settings(
    settings: Annotated[Settings, Depends(get_settings)],
) -> SettingsResponseSchema:
    """Get current settings.

    Returns the editable subset of application settings.
    Sensitive values like API keys are masked.
    """
    return SettingsResponseSchema(
        settings=_settings_to_schema(settings),
        config_path=str(CONFIG_PATH.absolute()),
        restart_required=False,
    )


@router.put("", response_model=SettingsResponseSchema)
async def update_settings(
    update: SettingsUpdateSchema,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SettingsResponseSchema:
    """Update settings.

    Changes are saved to config.yaml and require a restart to take effect.
    Only provided fields are updated; omitted sections are unchanged.
    """
    # Load existing config
    config = _load_config_yaml()

    changes_made = False

    # Update model settings
    if update.model is not None:
        if "model" not in config:
            config["model"] = {}

        model_updates = update.model.model_dump()
        for key, value in model_updates.items():
            if config["model"].get(key) != value:
                config["model"][key] = value
                changes_made = True
                logger.info("settings_updated", section="model", key=key, value=value)

    # Update evidence settings
    if update.evidence is not None:
        if "evidence" not in config:
            config["evidence"] = {}

        evidence_updates = update.evidence.model_dump()
        for key, value in evidence_updates.items():
            if config["evidence"].get(key) != value:
                config["evidence"][key] = value
                changes_made = True
                logger.info("settings_updated", section="evidence", key=key, value=value)

    # Update webhook settings
    if update.webhook is not None:
        if "webhook" not in config:
            config["webhook"] = {}

        webhook_updates = update.webhook.model_dump()
        for key, value in webhook_updates.items():
            # Don't overwrite existing key with masked value
            if key == "ifttt_key" and value.startswith("••"):
                continue
            # Don't overwrite with empty string if there's an existing key
            if key == "ifttt_key" and not value and config["webhook"].get("ifttt_key"):
                continue

            if config["webhook"].get(key) != value:
                config["webhook"][key] = value
                changes_made = True
                # Don't log sensitive values
                log_value = "***" if key == "ifttt_key" else value
                logger.info("settings_updated", section="webhook", key=key, value=log_value)

    # Update quiet hours settings
    if update.quiet_hours is not None:
        if "quiet_hours" not in config:
            config["quiet_hours"] = {}

        quiet_hours_updates = update.quiet_hours.model_dump()
        for key, value in quiet_hours_updates.items():
            if config["quiet_hours"].get(key) != value:
                config["quiet_hours"][key] = value
                changes_made = True
                logger.info("settings_updated", section="quiet_hours", key=key, value=value)

    # Save to file
    if changes_made:
        _save_config_yaml(config)
        logger.info("config_file_saved", path=str(CONFIG_PATH))

    return SettingsResponseSchema(
        settings=_settings_to_schema(settings),
        config_path=str(CONFIG_PATH.absolute()),
        restart_required=changes_made,
        message="Settings saved. Restart required for changes to take effect." if changes_made else None,
    )
