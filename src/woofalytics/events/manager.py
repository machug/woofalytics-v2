"""Central notification management with thread pool offloading."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

from woofalytics.config import Settings
from woofalytics.events.debouncer import NotificationDebouncer
from woofalytics.events.models import NotificationEvent
from woofalytics.events.webhook import WebhookNotifier

logger = structlog.get_logger(__name__)

# Dedicated thread pool for notifications (don't block detector)
NOTIFICATION_THREAD_POOL = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="notif-",
)


@dataclass
class NotificationManager:
    """Orchestrates notification delivery via thread pool.

    Key design:
    - Called from fingerprint processor with dog context already available
    - Immediately offloads to thread pool (no async DB queries)
    - All blocking work (debounce check, HTTP calls) runs in thread
    """

    settings: Settings

    # Components (initialized in start())
    _webhook: WebhookNotifier | None = field(default=None, init=False)
    _debouncer: NotificationDebouncer | None = field(default=None, init=False)

    # Stats
    _events_received: int = field(default=0, init=False)
    _notifications_sent: int = field(default=0, init=False)

    def start(self) -> None:
        """Initialize notification system (sync - called during startup)."""
        if not self.settings.notification.enabled:
            logger.info("notification_system_disabled")
            return

        if not self.settings.webhook.enabled:
            logger.info("notification_system_enabled_but_no_channels")
            return

        # Initialize debouncer
        self._debouncer = NotificationDebouncer(
            debounce_seconds=self.settings.webhook.debounce_seconds,
        )

        # Initialize webhook notifier
        self._webhook = WebhookNotifier(self.settings.webhook)
        self._webhook.start()

        logger.info("notification_manager_started")

    def stop(self) -> None:
        """Shutdown notification system (sync - called during shutdown)."""
        if self._webhook:
            self._webhook.stop()

        logger.info(
            "notification_manager_stopped",
            events_received=self._events_received,
            notifications_sent=self._notifications_sent,
        )

    def notify(
        self,
        timestamp: datetime,
        probability: float,
        doa_degrees: int | None = None,
        dog_id: str | None = None,
        dog_name: str | None = None,
        match_confidence: float | None = None,
        evidence_filename: str | None = None,
    ) -> None:
        """Submit a bark event for notification (non-blocking).

        Called from fingerprint processor AFTER dog matching is complete.
        This ensures we have dog context without doing DB queries here.

        Immediately offloads to thread pool - does not block.
        """
        if not self._webhook or not self._debouncer:
            return

        self._events_received += 1

        # Create immutable event snapshot
        event = NotificationEvent(
            timestamp=timestamp,
            probability=probability,
            doa_degrees=doa_degrees,
            dog_id=dog_id,
            dog_name=dog_name,
            match_confidence=match_confidence,
            evidence_filename=evidence_filename,
        )

        # Offload all work to thread pool
        NOTIFICATION_THREAD_POOL.submit(self._process_notification_sync, event)

    def _process_notification_sync(self, event: NotificationEvent) -> None:
        """Process notification in thread pool (blocking).

        This runs in a dedicated thread, not the async event loop.
        Safe to do blocking operations here.
        """
        try:
            # Check debouncing
            if not self._debouncer.should_notify(event.dog_id, event.timestamp):
                return

            # Send notification
            if self._webhook.notify(event):
                self._notifications_sent += 1
                logger.info(
                    "notification_sent",
                    dog_name=event.dog_name,
                    dog_id=event.dog_id,
                )

        except Exception as e:
            logger.error(
                "notification_processing_error",
                error=str(e),
                error_type=type(e).__name__,
            )

    def get_stats(self) -> dict[str, Any]:
        """Get notification system statistics."""
        stats: dict[str, Any] = {
            "enabled": self.settings.notification.enabled,
            "events_received": self._events_received,
            "notifications_sent": self._notifications_sent,
        }

        if self._debouncer:
            stats["debouncer"] = self._debouncer.get_stats()

        if self._webhook:
            stats["webhook"] = self._webhook.get_stats()

        return stats
