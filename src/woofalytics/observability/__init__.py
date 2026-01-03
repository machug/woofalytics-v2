"""Observability components for Woofalytics.

This module provides Prometheus metrics for monitoring the bark detection
pipeline, including counters, histograms, and gauges for key operational
metrics.
"""

from woofalytics.observability.metrics import (
    MetricsRegistry,
    get_metrics,
    instrument_detector,
)

__all__ = ["MetricsRegistry", "get_metrics", "instrument_detector"]
