"""Event notification modules for bark alerts.

This package provides webhook notifications for bark events via:
- IFTTT Maker Webhooks (push, email, SMS via IFTTT applets)
- Custom webhooks (Home Assistant, Slack, etc.)
"""

from woofalytics.events.manager import NotificationManager
from woofalytics.events.models import NotificationEvent

__all__ = ["NotificationEvent", "NotificationManager"]
