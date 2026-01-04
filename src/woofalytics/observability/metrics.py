"""Prometheus metrics for Woofalytics.

This module defines Prometheus metrics for monitoring the bark detection
pipeline, including:
- Counters: bark_detections_total, inference_total, vad_skipped_total
- Histograms: inference_latency_seconds, audio_energy_db
- Gauges: detector_running, bark_probability_current

Usage:
    from woofalytics.observability.metrics import get_metrics, instrument_detector

    # Get the global metrics registry
    metrics = get_metrics()

    # Instrument a BarkDetector instance
    instrument_detector(detector)

    # Access metrics directly
    metrics.bark_detections_total.inc()
    metrics.inference_latency.observe(0.123)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable

import structlog

if TYPE_CHECKING:
    from woofalytics.detection.model import BarkDetector, BarkEvent

logger = structlog.get_logger(__name__)

# Lazy import prometheus_client to avoid import errors if not installed
_prometheus_client: Any = None


def _get_prometheus() -> Any:
    """Lazy load prometheus_client module."""
    global _prometheus_client
    if _prometheus_client is None:
        try:
            import prometheus_client
            _prometheus_client = prometheus_client
        except ImportError:
            logger.warning(
                "prometheus_client not installed, metrics will be no-ops",
                hint="pip install prometheus-client",
            )
            _prometheus_client = False
    return _prometheus_client


@dataclass
class MetricsRegistry:
    """Registry of Prometheus metrics for Woofalytics.

    This class holds all the metrics used to monitor the detection pipeline.
    Metrics are created lazily to handle missing prometheus_client gracefully.
    """

    _initialized: bool = field(default=False, init=False)

    # Counters
    _bark_detections_total: Any = field(default=None, init=False)
    _inference_total: Any = field(default=None, init=False)
    _vad_skipped_total: Any = field(default=None, init=False)
    _yamnet_skipped_total: Any = field(default=None, init=False)
    _speech_vetoed_total: Any = field(default=None, init=False)

    # Histograms
    _inference_latency: Any = field(default=None, init=False)
    _yamnet_latency: Any = field(default=None, init=False)
    _audio_energy_db: Any = field(default=None, init=False)
    _bark_probability: Any = field(default=None, init=False)

    # Gauges
    _detector_running: Any = field(default=None, init=False)
    _uptime_seconds: Any = field(default=None, init=False)
    _total_barks_gauge: Any = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize Prometheus metrics."""
        prom = _get_prometheus()
        if not prom:
            self._initialized = False
            return

        # Counters
        self._bark_detections_total = prom.Counter(
            "woofalytics_bark_detections_total",
            "Total number of bark detections",
        )
        self._inference_total = prom.Counter(
            "woofalytics_inference_total",
            "Total number of inference runs",
            ["model_type"],  # "clap" or "legacy"
        )
        self._vad_skipped_total = prom.Counter(
            "woofalytics_vad_skipped_total",
            "Total number of inferences skipped by VAD gate",
        )
        self._yamnet_skipped_total = prom.Counter(
            "woofalytics_yamnet_skipped_total",
            "Total number of inferences skipped by YAMNet pre-filter",
        )
        self._speech_vetoed_total = prom.Counter(
            "woofalytics_speech_vetoed_total",
            "Total number of barks vetoed due to speech detection",
        )

        # Histograms
        self._inference_latency = prom.Histogram(
            "woofalytics_inference_latency_seconds",
            "Inference latency in seconds",
            ["model_type"],
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
        )
        self._yamnet_latency = prom.Histogram(
            "woofalytics_yamnet_inference_seconds",
            "YAMNet inference latency in seconds",
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25),
        )
        self._audio_energy_db = prom.Histogram(
            "woofalytics_audio_energy_db",
            "Audio RMS energy in dBFS",
            buckets=(-60, -50, -40, -30, -20, -10, -5, 0),
        )
        self._bark_probability = prom.Histogram(
            "woofalytics_bark_probability",
            "Bark detection probability distribution",
            buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
        )

        # Gauges
        self._detector_running = prom.Gauge(
            "woofalytics_detector_running",
            "Whether the bark detector is running (1) or stopped (0)",
        )
        self._uptime_seconds = prom.Gauge(
            "woofalytics_uptime_seconds",
            "Detector uptime in seconds",
        )
        self._total_barks_gauge = prom.Gauge(
            "woofalytics_total_barks",
            "Total number of barks detected (gauge for current value)",
        )

        self._initialized = True
        logger.info("prometheus_metrics_initialized")

    @property
    def is_initialized(self) -> bool:
        """Check if metrics are initialized."""
        return self._initialized

    # Counter accessors
    @property
    def bark_detections_total(self) -> Any:
        """Counter for total bark detections."""
        return self._bark_detections_total

    @property
    def inference_total(self) -> Any:
        """Counter for total inferences (labeled by model_type)."""
        return self._inference_total

    @property
    def vad_skipped_total(self) -> Any:
        """Counter for VAD-skipped inferences."""
        return self._vad_skipped_total

    @property
    def yamnet_skipped_total(self) -> Any:
        """Counter for YAMNet-skipped inferences."""
        return self._yamnet_skipped_total

    @property
    def speech_vetoed_total(self) -> Any:
        """Counter for speech-vetoed detections."""
        return self._speech_vetoed_total

    # Histogram accessors
    @property
    def inference_latency(self) -> Any:
        """Histogram for inference latency."""
        return self._inference_latency

    @property
    def yamnet_latency(self) -> Any:
        """Histogram for YAMNet inference latency."""
        return self._yamnet_latency

    @property
    def audio_energy_db(self) -> Any:
        """Histogram for audio energy levels."""
        return self._audio_energy_db

    @property
    def bark_probability_hist(self) -> Any:
        """Histogram for bark probability distribution."""
        return self._bark_probability

    # Gauge accessors
    @property
    def detector_running(self) -> Any:
        """Gauge for detector running status."""
        return self._detector_running

    @property
    def uptime_seconds(self) -> Any:
        """Gauge for detector uptime."""
        return self._uptime_seconds

    @property
    def total_barks_gauge(self) -> Any:
        """Gauge for total barks (current value)."""
        return self._total_barks_gauge

    def inc_bark_detection(self) -> None:
        """Increment bark detection counter."""
        if self._bark_detections_total:
            self._bark_detections_total.inc()

    def inc_inference(self, model_type: str = "clap") -> None:
        """Increment inference counter."""
        if self._inference_total:
            self._inference_total.labels(model_type=model_type).inc()

    def inc_vad_skipped(self) -> None:
        """Increment VAD skipped counter."""
        if self._vad_skipped_total:
            self._vad_skipped_total.inc()

    def inc_yamnet_skipped(self) -> None:
        """Increment YAMNet skipped counter."""
        if self._yamnet_skipped_total:
            self._yamnet_skipped_total.inc()

    def observe_yamnet_latency(self, seconds: float) -> None:
        """Record YAMNet inference latency."""
        if self._yamnet_latency:
            self._yamnet_latency.observe(seconds)

    def inc_speech_vetoed(self) -> None:
        """Increment speech vetoed counter."""
        if self._speech_vetoed_total:
            self._speech_vetoed_total.inc()

    def observe_latency(self, seconds: float, model_type: str = "clap") -> None:
        """Record inference latency."""
        if self._inference_latency:
            self._inference_latency.labels(model_type=model_type).observe(seconds)

    def observe_energy(self, db: float) -> None:
        """Record audio energy level."""
        if self._audio_energy_db:
            self._audio_energy_db.observe(db)

    def observe_probability(self, prob: float) -> None:
        """Record bark probability."""
        if self._bark_probability:
            self._bark_probability.observe(prob)

    def set_running(self, running: bool) -> None:
        """Set detector running status."""
        if self._detector_running:
            self._detector_running.set(1 if running else 0)

    def set_uptime(self, seconds: float) -> None:
        """Set current uptime."""
        if self._uptime_seconds:
            self._uptime_seconds.set(seconds)

    def set_total_barks(self, count: int) -> None:
        """Set total barks gauge."""
        if self._total_barks_gauge:
            self._total_barks_gauge.set(count)


# Global metrics registry singleton
_metrics_registry: MetricsRegistry | None = None


def get_metrics() -> MetricsRegistry:
    """Get the global metrics registry.

    Returns:
        The singleton MetricsRegistry instance.
    """
    global _metrics_registry
    if _metrics_registry is None:
        _metrics_registry = MetricsRegistry()
    return _metrics_registry


def instrument_detector(detector: BarkDetector) -> None:
    """Instrument a BarkDetector with Prometheus metrics.

    This adds a callback to the detector that updates metrics
    on each detection event.

    Args:
        detector: The BarkDetector instance to instrument.
    """
    metrics = get_metrics()
    if not metrics.is_initialized:
        logger.warning("metrics_not_initialized", reason="prometheus_client not available")
        return

    def on_bark_event(event: BarkEvent) -> None:
        """Callback to update metrics on each detection event."""
        # Update probability histogram
        metrics.observe_probability(event.probability)

        # Update bark counter if detected
        if event.is_barking:
            metrics.inc_bark_detection()

        # Update gauges
        metrics.set_running(detector.is_running)
        metrics.set_uptime(detector.uptime_seconds)
        metrics.set_total_barks(detector.total_barks_detected)

    detector.add_callback(on_bark_event)
    logger.info("detector_instrumented_with_metrics")


def generate_latest() -> bytes:
    """Generate Prometheus metrics in text format.

    Returns:
        Metrics in Prometheus text exposition format.
    """
    prom = _get_prometheus()
    if not prom:
        return b"# prometheus_client not installed\n"
    return prom.generate_latest()


def time_inference(model_type: str = "clap") -> Callable:
    """Decorator to time inference and record metrics.

    Args:
        model_type: The model type label ("clap" or "legacy").

    Returns:
        Decorator function.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            metrics = get_metrics()
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                elapsed = time.perf_counter() - start
                metrics.observe_latency(elapsed, model_type)
                metrics.inc_inference(model_type)
        return wrapper
    return decorator
