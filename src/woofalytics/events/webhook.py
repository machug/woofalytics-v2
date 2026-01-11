"""Webhook notification delivery using httpx (sync for thread pool)."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

from woofalytics.config import WebhookConfig
from woofalytics.events.models import NotificationEvent

logger = structlog.get_logger(__name__)

# IFTTT Maker Webhooks endpoint (allowlisted)
IFTTT_URL_TEMPLATE = "https://maker.ifttt.com/trigger/{event}/with/key/{key}"


@dataclass
class WebhookNotifier:
    """Sends notifications via webhooks (IFTTT and custom).

    Uses sync httpx client since this runs in thread pool.
    """

    config: WebhookConfig
    _client: httpx.Client | None = field(default=None, init=False)
    _send_count: int = field(default=0, init=False)
    _error_count: int = field(default=0, init=False)

    def start(self) -> None:
        """Initialize the HTTP client with connection limits."""
        self._client = httpx.Client(
            timeout=httpx.Timeout(self.config.timeout_seconds),
            follow_redirects=False,  # Security: don't follow redirects
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
            ),
        )
        logger.info("webhook_notifier_started")

    def stop(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None
        logger.info(
            "webhook_notifier_stopped",
            sent=self._send_count,
            errors=self._error_count,
        )

    def notify(self, event: NotificationEvent) -> bool:
        """Send notification via configured webhooks.

        Runs in thread pool - uses sync httpx.
        Returns True if at least one webhook succeeded.
        """
        if not self._client:
            logger.warning("webhook_client_not_initialized")
            return False

        success = False

        # Send to IFTTT if configured
        ifttt_key = self.config.ifttt_key.get_secret_value()
        if ifttt_key and self._send_ifttt(event, ifttt_key):
            success = True

        # Send to custom URL if configured
        if self.config.custom_url and self._send_custom(event):
            success = True

        return success

    def _send_ifttt(self, event: NotificationEvent, key: str) -> bool:
        """Send to IFTTT Maker Webhooks."""
        url = IFTTT_URL_TEMPLATE.format(
            event=self.config.ifttt_event,
            key=key,
        )
        payload = event.to_ifttt_values()

        return self._send_with_retry(
            url=url,
            json=payload,
            name="ifttt",
        )

    def _send_custom(self, event: NotificationEvent) -> bool:
        """Send to custom webhook URL."""
        if not self.config.custom_url:
            return False

        payload = event.to_webhook_payload()

        # Build headers
        headers = dict(self.config.custom_headers)

        # Add auth token if configured
        auth_token = self.config.custom_auth_token.get_secret_value()
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        return self._send_with_retry(
            url=self.config.custom_url,
            json=payload,
            headers=headers,
            name="custom",
        )

    def _send_with_retry(
        self,
        url: str,
        json: dict[str, Any],
        headers: dict[str, str] | None = None,
        name: str = "webhook",
    ) -> bool:
        """Send HTTP POST with exponential backoff retry.

        Best practices:
        - Exponential backoff with jitter
        - Retry on 5xx and network errors
        - Don't retry on 4xx (client errors)
        - Don't follow redirects (SSRF protection)
        """
        last_error: str | None = None

        for attempt in range(self.config.retry_count + 1):
            try:
                response = self._client.post(
                    url,
                    json=json,
                    headers=headers,
                )

                if response.status_code < 400:
                    self._send_count += 1
                    logger.info(
                        "webhook_sent",
                        name=name,
                        status=response.status_code,
                        attempt=attempt + 1,
                    )
                    return True

                # Client error - don't retry
                if 400 <= response.status_code < 500:
                    self._error_count += 1
                    logger.warning(
                        "webhook_client_error",
                        name=name,
                        status=response.status_code,
                        body=response.text[:200],
                    )
                    return False

                # Server error - retry
                last_error = f"HTTP {response.status_code}"

            except httpx.TimeoutException as e:
                last_error = f"Timeout: {e}"
            except httpx.NetworkError as e:
                last_error = f"Network: {e}"
            except httpx.HTTPError as e:
                last_error = f"HTTP: {e}"

            # Calculate backoff with jitter
            if attempt < self.config.retry_count:
                base_delay = min(2 ** attempt, 10)  # Max 10 seconds
                jitter = random.uniform(0, base_delay * 0.3)
                delay = base_delay + jitter

                logger.debug(
                    "webhook_retry",
                    name=name,
                    attempt=attempt + 1,
                    delay=round(delay, 1),
                    error=last_error,
                )
                time.sleep(delay)

        self._error_count += 1
        logger.error(
            "webhook_failed",
            name=name,
            attempts=self.config.retry_count + 1,
            error=last_error,
        )
        return False

    def get_stats(self) -> dict[str, Any]:
        """Get webhook statistics."""
        return {
            "sent": self._send_count,
            "errors": self._error_count,
            "ifttt_configured": bool(self.config.ifttt_key.get_secret_value()),
            "custom_url_configured": bool(self.config.custom_url),
        }
