"""Data models for notification events."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class NotificationEvent:
    """A notification-ready bark event with dog context.

    This is an immutable snapshot passed to the thread pool.
    All data needed for notification is included - no DB lookups required.
    """

    # Timing
    timestamp: datetime

    # Detection
    probability: float
    doa_degrees: int | None = None

    # Dog context (from fingerprint matcher)
    dog_id: str | None = None
    dog_name: str | None = None
    match_confidence: float | None = None

    # Evidence link
    evidence_filename: str | None = None

    def to_webhook_payload(self) -> dict[str, Any]:
        """Format for custom webhook delivery."""
        return {
            "event": "bark_detected",
            "timestamp": self.timestamp.isoformat(),
            "dog": {
                "id": self.dog_id,
                "name": self.dog_name or "Unknown",
                "confidence": round(self.match_confidence, 3) if self.match_confidence else None,
            },
            "detection": {
                "probability": round(self.probability, 3),
                "direction_degrees": self.doa_degrees,
            },
            "evidence_file": self.evidence_filename,
        }

    def to_ifttt_values(self) -> dict[str, str]:
        """Format for IFTTT Maker Webhooks (value1, value2, value3)."""
        return {
            "value1": self.dog_name or "Unknown Dog",
            "value2": self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "value3": f"{round(self.probability * 100)}% confidence",
        }
