"""Bark detection ML model and inference.

This module handles loading the detection model and running
inference on audio frames. Supports both CLAP (zero-shot) and
legacy MLP models.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import structlog
import torch

from woofalytics.audio.capture import AsyncAudioCapture
from woofalytics.config import Settings
from woofalytics.detection.clap import CLAPConfig, CLAPDetector
from woofalytics.detection.doa import DirectionEstimator
from woofalytics.detection.features import FeatureExtractor, create_default_extractor
from woofalytics.detection.vad import VADConfig, VADGate
from woofalytics.observability.metrics import get_metrics

logger = structlog.get_logger(__name__)


@dataclass
class BarkEvent:
    """A bark detection event."""

    timestamp: datetime
    probability: float
    is_barking: bool
    doa_bartlett: int | None = None
    doa_capon: int | None = None
    doa_mem: int | None = None
    audio: np.ndarray | None = None  # Raw audio for fingerprint extraction
    sample_rate: int = 48000

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "probability": self.probability,
            "is_barking": self.is_barking,
            "doa_bartlett": self.doa_bartlett,
            "doa_capon": self.doa_capon,
            "doa_mem": self.doa_mem,
        }


@dataclass
class BarkDetector:
    """Main bark detection orchestrator.

    This class coordinates audio capture, feature extraction,
    model inference, and event handling.

    Supports two detection backends:
    - CLAP: Zero-shot audio classification (recommended, better speech rejection)
    - Legacy MLP: TorchScript traced model (requires traced_model.pt)
    """

    settings: Settings

    # Private state
    _model: torch.jit.ScriptModule | None = field(default=None, init=False)
    _clap_detector: CLAPDetector | None = field(default=None, init=False)
    _vad_gate: VADGate | None = field(default=None, init=False)
    _feature_extractor: FeatureExtractor | None = field(default=None, init=False)
    _doa_estimator: DirectionEstimator | None = field(default=None, init=False)
    _audio_capture: AsyncAudioCapture | None = field(default=None, init=False)
    _running: bool = field(default=False, init=False)
    _inference_task: asyncio.Task | None = field(default=None, init=False)
    _last_event: BarkEvent | None = field(default=None, init=False)
    _event_history: deque[BarkEvent] = field(
        default_factory=lambda: deque(maxlen=100), init=False
    )
    _callbacks: list[Callable[[BarkEvent], None]] = field(default_factory=list, init=False)
    _start_time: float = field(default=0.0, init=False)
    _total_barks: int = field(default=0, init=False)
    _inference_count: int = field(default=0, init=False)
    _vad_skipped_count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.settings.model.use_clap:
            self._load_clap_model()
        else:
            self._load_model()
            self._setup_components()

    def _load_clap_model(self) -> None:
        """Load the CLAP zero-shot audio classifier."""
        config = CLAPConfig(
            model_name=self.settings.model.clap_model,
            threshold=self.settings.model.clap_threshold,
            bird_veto_threshold=self.settings.model.clap_bird_veto_threshold,
            device=self.settings.model.clap_device,
        )
        self._clap_detector = CLAPDetector(config)
        # Lazy loading - model loads on first inference
        logger.info(
            "clap_detector_configured",
            model=config.model_name,
            threshold=config.threshold,
            bird_veto_threshold=config.bird_veto_threshold,
            device=config.device,
        )

        # Initialize VAD gate for fast rejection of silent frames
        if self.settings.model.vad_enabled:
            vad_config = VADConfig(
                energy_threshold_db=self.settings.model.vad_threshold_db,
            )
            self._vad_gate = VADGate(vad_config)
            logger.info(
                "vad_gate_enabled",
                threshold_db=self.settings.model.vad_threshold_db,
            )

        # Still set up DOA estimator for direction detection
        if self.settings.doa.enabled:
            self._doa_estimator = DirectionEstimator(
                element_spacing=self.settings.doa.element_spacing,
                num_elements=self.settings.doa.num_elements,
                angle_min=self.settings.doa.angle_min,
                angle_max=self.settings.doa.angle_max,
                method=self.settings.doa.method,
            )

    def _load_model(self) -> None:
        """Load the TorchScript model (legacy)."""
        model_path = Path(self.settings.model.path)

        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        logger.info("loading_legacy_model", path=str(model_path))
        self._model = torch.jit.load(str(model_path))
        self._model.eval()
        logger.info("legacy_model_loaded")

    def _setup_components(self) -> None:
        """Initialize feature extractor and DOA estimator."""
        self._feature_extractor = create_default_extractor(
            source_sample_rate=self.settings.audio.sample_rate
        )

        if self.settings.doa.enabled:
            self._doa_estimator = DirectionEstimator(
                element_spacing=self.settings.doa.element_spacing,
                num_elements=self.settings.doa.num_elements,
                angle_min=self.settings.doa.angle_min,
                angle_max=self.settings.doa.angle_max,
                method=self.settings.doa.method,
            )

    @property
    def audio_capture(self) -> AsyncAudioCapture | None:
        """Get the audio capture instance (available after start())."""
        return self._audio_capture

    async def start(self) -> None:
        """Start the bark detector.

        This starts audio capture and begins running inference.
        """
        if self._running:
            logger.warning("detector_already_running")
            return

        self._running = True
        self._start_time = time.time()

        # Start audio capture
        self._audio_capture = AsyncAudioCapture(config=self.settings.audio)
        await self._audio_capture.start()

        # Start inference loop
        self._inference_task = asyncio.create_task(self._inference_loop())

        logger.info("bark_detector_started")

    async def stop(self) -> None:
        """Stop the bark detector."""
        if not self._running:
            return

        self._running = False

        # Stop inference task
        if self._inference_task:
            self._inference_task.cancel()
            try:
                await self._inference_task
            except asyncio.CancelledError:
                pass

        # Stop audio capture
        if self._audio_capture:
            await self._audio_capture.stop()

        logger.info("bark_detector_stopped")

    async def _inference_loop(self) -> None:
        """Main inference loop."""
        # CLAP uses ~1s audio windows and is slower, so run less frequently
        # Legacy MLP uses 80ms windows and is fast
        if self.settings.model.use_clap:
            interval = 0.5  # 500ms - CLAP needs more audio and is heavier
        else:
            interval = 0.08  # 80ms for legacy MLP

        while self._running:
            try:
                await self._run_inference()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("inference_error", error=str(e))
                await asyncio.sleep(0.1)

    async def _run_inference(self) -> None:
        """Run a single inference on recent audio."""
        if self.settings.model.use_clap:
            await self._run_clap_inference()
        else:
            await self._run_legacy_inference()

    async def _run_clap_inference(self) -> None:
        """Run inference using CLAP zero-shot classifier."""
        if not self._audio_capture or not self._clap_detector:
            logger.warning("clap_inference_skipped", reason="missing audio_capture or clap_detector")
            return

        # CLAP needs more audio context (~1 second for good classification)
        # At 44100 Hz with 441 samples per chunk = 10ms per chunk
        # 100 chunks = 1 second of audio
        frames = self._audio_capture.get_recent_frames(count=100)
        if len(frames) < 50:  # Need at least 500ms
            logger.debug("clap_inference_waiting", frames=len(frames), needed=50)
            return

        # Combine frames into single array
        audio_data = b"".join(f.data for f in frames)
        audio_array = np.frombuffer(audio_data, dtype=np.int16)

        # Reshape to (channels, samples)
        channels = self.settings.audio.channels
        audio_array = audio_array.reshape((channels, -1), order="F")

        # Get metrics registry
        metrics = get_metrics()

        # VAD gate: skip CLAP inference on silent audio
        if self._vad_gate and not self._vad_gate.is_active(audio_array):
            self._vad_skipped_count += 1
            metrics.inc_vad_skipped()
            # Log VAD skip rate periodically
            if self._vad_skipped_count % 50 == 0:
                logger.debug(
                    "vad_skipping_silent_frames",
                    skipped=self._vad_skipped_count,
                    vad_stats=self._vad_gate.stats,
                )
            return

        # Extract DOA if enabled
        doa_bartlett, doa_capon, doa_mem = None, None, None
        if self._doa_estimator and channels >= 2:
            doa_bartlett, doa_capon, doa_mem = self._doa_estimator.estimate(audio_array)

        # Run CLAP detection with latency tracking
        inference_start = time.perf_counter()
        try:
            probability, is_barking, label_scores = self._clap_detector.detect(
                audio_array,
                sample_rate=self.settings.audio.sample_rate,
            )
        except Exception as e:
            logger.warning("clap_inference_error", error=str(e), error_type=type(e).__name__)
            return
        finally:
            inference_latency = time.perf_counter() - inference_start
            metrics.observe_latency(inference_latency, model_type="clap")
            metrics.inc_inference(model_type="clap")

        # Create event - include audio for fingerprint extraction when barking
        event = BarkEvent(
            timestamp=datetime.now(),
            probability=probability,
            is_barking=is_barking,
            doa_bartlett=doa_bartlett,
            doa_capon=doa_capon,
            doa_mem=doa_mem,
            audio=audio_array if is_barking else None,
            sample_rate=self.settings.audio.sample_rate,
        )

        self._last_event = event
        self._inference_count += 1

        # Log periodic status (every 20 inferences = ~10 seconds)
        if self._inference_count % 20 == 0:
            top_label = max(label_scores, key=label_scores.get) if label_scores else "unknown"
            logger.info(
                "clap_inference_status",
                count=self._inference_count,
                probability=f"{probability:.3f}",
                top_label=top_label,
                total_barks=self._total_barks,
            )

        # Record probability in histogram
        metrics.observe_probability(probability)

        # Track barks
        if is_barking:
            self._total_barks += 1
            metrics.inc_bark_detection()
            # Log all scores for debugging speech veto effectiveness
            logger.info(
                "bark_detected",
                probability=f"{probability:.3f}",
                doa=doa_bartlett,
                scores={k: f"{v:.3f}" for k, v in sorted(label_scores.items(), key=lambda x: -x[1])[:5]},
            )
        elif probability >= self.settings.model.clap_threshold:
            # Bark was above threshold but vetoed (likely by speech detection)
            metrics.inc_speech_vetoed()
            logger.info(
                "bark_vetoed",
                probability=f"{probability:.3f}",
                scores={k: f"{v:.3f}" for k, v in sorted(label_scores.items(), key=lambda x: -x[1])[:5]},
            )

        # Keep history
        self._event_history.append(event)

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.warning("callback_error", error=str(e))

    async def _run_legacy_inference(self) -> None:
        """Run inference using legacy TorchScript MLP model."""
        if not self._audio_capture or not self._model or not self._feature_extractor:
            return

        # Get recent audio frames (need about 80ms of audio)
        frames = self._audio_capture.get_recent_frames(count=8)
        if len(frames) < 8:
            return  # Not enough data yet

        # Combine frames into single array
        audio_data = b"".join(f.data for f in frames)
        audio_array = np.frombuffer(audio_data, dtype=np.int16)

        # Reshape to (channels, samples)
        channels = self.settings.audio.channels
        audio_array = audio_array.reshape((channels, -1), order="F")

        # Extract DOA if enabled
        doa_bartlett, doa_capon, doa_mem = None, None, None
        if self._doa_estimator and channels >= 2:
            doa_bartlett, doa_capon, doa_mem = self._doa_estimator.estimate(audio_array)

        # Get metrics registry
        metrics = get_metrics()

        # Extract features and run inference with latency tracking
        inference_start = time.perf_counter()
        try:
            features = self._feature_extractor.extract_from_int16(audio_array)

            # Expected size check
            expected_size = 480  # 6 frames * 80 mels
            if features.shape[1] != expected_size:
                logger.debug(
                    "feature_size_mismatch",
                    expected=expected_size,
                    actual=features.shape[1],
                )
                return

            # Run inference
            with torch.inference_mode():
                probability = self._model(features).item()

        except Exception as e:
            logger.debug("feature_extraction_error", error=str(e))
            return
        finally:
            inference_latency = time.perf_counter() - inference_start
            metrics.observe_latency(inference_latency, model_type="legacy")
            metrics.inc_inference(model_type="legacy")

        # Create event
        is_barking = probability >= self.settings.model.threshold
        event = BarkEvent(
            timestamp=datetime.now(),
            probability=probability,
            is_barking=is_barking,
            doa_bartlett=doa_bartlett,
            doa_capon=doa_capon,
            doa_mem=doa_mem,
        )

        self._last_event = event

        # Record probability in histogram
        metrics.observe_probability(probability)

        # Track barks
        if is_barking:
            self._total_barks += 1
            metrics.inc_bark_detection()
            logger.info(
                "bark_detected",
                probability=f"{probability:.3f}",
                doa=doa_bartlett,
            )

        # Keep history (deque with maxlen=100 auto-discards oldest)
        self._event_history.append(event)

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.warning("callback_error", error=str(e))

    def get_last_event(self) -> BarkEvent | None:
        """Get the most recent bark detection event."""
        return self._last_event

    def get_recent_events(self, count: int = 10) -> list[BarkEvent]:
        """Get recent bark detection events."""
        return list(self._event_history)[-count:]

    def add_callback(self, callback: Callable[[BarkEvent], None]) -> None:
        """Add a callback to be called on each detection event."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[BarkEvent], None]) -> None:
        """Remove a previously added callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    @property
    def is_running(self) -> bool:
        """Check if detector is running."""
        return self._running

    @property
    def uptime_seconds(self) -> float:
        """Get uptime in seconds."""
        if self._start_time == 0:
            return 0.0
        return time.time() - self._start_time

    @property
    def total_barks_detected(self) -> int:
        """Get total number of barks detected."""
        return self._total_barks

    def get_status(self) -> dict:
        """Get detector status as dictionary."""
        status = {
            "running": self._running,
            "uptime_seconds": self.uptime_seconds,
            "total_barks": self._total_barks,
            "last_event": self._last_event.to_dict() if self._last_event else None,
            "microphone": (
                self._audio_capture.microphone.name
                if self._audio_capture and self._audio_capture.microphone
                else None
            ),
        }

        # Include VAD stats if enabled
        if self._vad_gate:
            status["vad_stats"] = self._vad_gate.stats

        return status
