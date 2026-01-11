"""Simple debouncing for notifications with bounded memory."""

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Memory bound: max dogs to track
MAX_TRACKED_DOGS = 1000


@dataclass
class NotificationDebouncer:
    """Simple per-dog rate limiting with LRU eviction.

    Thread-safe via lock since this runs in thread pool.
    Uses OrderedDict for LRU eviction when memory bound exceeded.
    """

    debounce_seconds: int = 300  # 5 minutes between notifications

    # State: dog_id -> last_notification_time
    # Using OrderedDict for LRU eviction
    _last_notification: OrderedDict[str, datetime] = field(
        default_factory=OrderedDict
    )
    _lock: Lock = field(default_factory=Lock)

    # Stats
    _total_checked: int = 0
    _total_debounced: int = 0

    def should_notify(self, dog_id: str | None, timestamp: datetime) -> bool:
        """Check if notification should be sent for this dog.

        Thread-safe. Returns True if notification should proceed.
        """
        key = dog_id or "__unknown__"

        with self._lock:
            self._total_checked += 1

            # Check if within debounce window
            if key in self._last_notification:
                last_time = self._last_notification[key]
                elapsed = (timestamp - last_time).total_seconds()

                if elapsed < self.debounce_seconds:
                    self._total_debounced += 1
                    logger.debug(
                        "notification_debounced",
                        dog_id=dog_id,
                        elapsed_seconds=round(elapsed),
                        debounce_seconds=self.debounce_seconds,
                    )
                    return False

                # Move to end (most recently used)
                self._last_notification.move_to_end(key)
            else:
                # New entry - check memory bound
                if len(self._last_notification) >= MAX_TRACKED_DOGS:
                    # Evict oldest (least recently used)
                    evicted_key, _ = self._last_notification.popitem(last=False)
                    logger.debug("debouncer_evicted", dog_id=evicted_key)

            # Update last notification time
            self._last_notification[key] = timestamp
            return True

    def get_stats(self) -> dict[str, Any]:
        """Get debouncer statistics."""
        with self._lock:
            return {
                "tracked_dogs": len(self._last_notification),
                "max_tracked": MAX_TRACKED_DOGS,
                "total_checked": self._total_checked,
                "total_debounced": self._total_debounced,
                "debounce_seconds": self.debounce_seconds,
            }
