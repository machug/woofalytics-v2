"""CLAP-based zero-shot bark detection.

This module uses the CLAP (Contrastive Language-Audio Pretraining) model
for zero-shot audio classification. CLAP can distinguish between dog barks
and human speech without any fine-tuning.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CLAPConfig:
    """Configuration for CLAP-based detection."""

    model_name: str = "laion/clap-htsat-unfused"

    # Labels for zero-shot classification
    # More specific labels to help distinguish real barks from speech
    positive_labels: list[str] = field(default_factory=lambda: [
        "dog barking loudly",
        "angry dog barking",
        "dog bark sound effect",
        "multiple dogs barking",
    ])

    # Speech labels that should veto bark detection
    speech_labels: list[str] = field(default_factory=lambda: [
        "human voice",
        "person speaking words",
        "man talking",
        "woman talking",
    ])

    # Percussive/keyboard labels that should veto bark detection
    percussive_labels: list[str] = field(default_factory=lambda: [
        "This is a sound of keyboard typing and clicking",
        "This is a sound of mechanical keyboard switches",
        "This is a sound of mouse clicking",
        "This is a sound of knocking on a surface",
        "This is a sound of tapping on a table",
    ])

    # Bird/nature labels that should veto bark detection
    # Birds are commonly misclassified as dog barks by CLAP
    bird_labels: list[str] = field(default_factory=lambda: [
        "bird chirping",
        "birds singing outside",
        "crow cawing loudly",
        "bird call sounds",
    ])

    # Other non-bark sounds
    other_labels: list[str] = field(default_factory=lambda: [
        "silence",
        "background noise",
        "music",
        "wind blowing",
        "traffic noise",
    ])

    # Threshold for bark detection (probability that it's a bark vs not)
    threshold: float = 0.5

    # If any speech label exceeds this, veto the bark detection
    speech_veto_threshold: float = 0.15

    # If any percussive label exceeds this, veto the bark detection
    percussive_veto_threshold: float = 0.20

    # If any bird label exceeds this, veto the bark detection
    bird_veto_threshold: float = 0.15

    # Bark score must beat best non-bark label by this margin
    confidence_margin: float = 0.10

    # Rolling window confirmation: require N positives out of last M detections
    rolling_window_size: int = 3
    rolling_window_min_positives: int = 2

    # Cooldown: minimum frames between bark detection events
    # Prevents rapid-fire 10x detections from a single sound
    detection_cooldown_frames: int = 5

    # Duration validation: reject events too short/long to be barks
    # Keyboard clicks are 10-50ms, dog barks are 100-1500ms
    duration_validation_enabled: bool = True
    min_duration_ms: float = 80
    max_duration_ms: float = 1500

    # HPSS pre-filter: reject predominantly percussive sounds (keyboard clicks)
    # Uses Harmonic-Percussive Source Separation to measure harmonic vs percussive energy
    hpss_enabled: bool = True
    min_harmonic_ratio: float = 0.5  # Barks > 2.0, clicks < 0.3

    # Device for inference
    device: str = "cpu"


class CLAPDetector:
    """Zero-shot bark detector using CLAP.

    CLAP computes similarity between audio and text descriptions,
    enabling classification without any training on bark data.

    Text embeddings are pre-computed and cached on load() to avoid
    redundant computation on every detect() call.
    """

    def __init__(self, config: CLAPConfig | None = None) -> None:
        """Initialize the CLAP detector.

        Args:
            config: Configuration for the detector. Uses defaults if None.
        """
        self.config = config or CLAPConfig()
        self._model: Any = None
        self._processor: Any = None
        self._device: Any = None
        self._all_labels: list[str] = []
        self._positive_indices: set[int] = set()
        self._speech_indices: set[int] = set()
        self._percussive_indices: set[int] = set()
        self._bird_indices: set[int] = set()
        # Cooldown counter to prevent rapid-fire detections
        self._cooldown_counter: int = 0
        # Rolling window to track recent detection results for confirmation
        self._detection_window: deque[bool] = deque(
            maxlen=self.config.rolling_window_size
        )

        # Cached text embeddings - computed once on load()
        self._cached_text_embeddings: Any = None

        # Temporal duration validator - initialized on load()
        self._temporal_validator: Any = None

        # Spectral pre-filter (HPSS) - initialized on load()
        self._spectral_prefilter: Any = None

    def load(self) -> None:
        """Load the CLAP model and pre-compute text embeddings.

        This is separate from __init__ to allow lazy loading.
        Text embeddings are computed once and cached for all future
        detect() calls, significantly reducing inference time.
        """
        import torch
        from transformers import ClapModel, ClapProcessor

        # Limit PyTorch threads to prevent CPU explosion
        torch.set_num_threads(4)
        torch.set_num_interop_threads(2)

        logger.info(
            "loading_clap_model",
            model=self.config.model_name,
            device=self.config.device,
        )

        # Determine device
        if self.config.device == "cuda" and torch.cuda.is_available():
            self._device = torch.device("cuda")
        else:
            self._device = torch.device("cpu")

        # Load model and processor directly (not pipeline) for embedding caching
        self._processor = ClapProcessor.from_pretrained(self.config.model_name)
        self._model = ClapModel.from_pretrained(self.config.model_name)
        self._model.to(self._device)
        self._model.eval()

        # Combine all labels: positive, speech (for veto), percussive (for veto), bird (for veto), and other
        self._all_labels = (
            self.config.positive_labels +
            self.config.speech_labels +
            self.config.percussive_labels +
            self.config.bird_labels +
            self.config.other_labels
        )
        self._positive_indices = set(range(len(self.config.positive_labels)))

        # Track speech label indices for veto logic
        speech_start = len(self.config.positive_labels)
        speech_end = speech_start + len(self.config.speech_labels)
        self._speech_indices = set(range(speech_start, speech_end))

        # Track percussive label indices for veto logic
        percussive_start = speech_end
        percussive_end = percussive_start + len(self.config.percussive_labels)
        self._percussive_indices = set(range(percussive_start, percussive_end))

        # Track bird label indices for veto logic
        bird_start = percussive_end
        bird_end = bird_start + len(self.config.bird_labels)
        self._bird_indices = set(range(bird_start, bird_end))

        # Pre-compute and cache text embeddings for all labels
        self._cache_text_embeddings()

        # Initialize temporal duration validator
        if self.config.duration_validation_enabled:
            from woofalytics.detection.features import TemporalValidator
            self._temporal_validator = TemporalValidator(
                min_duration_ms=self.config.min_duration_ms,
                max_duration_ms=self.config.max_duration_ms,
            )

        # Initialize HPSS spectral pre-filter
        if self.config.hpss_enabled:
            from woofalytics.detection.features import SpectralPreFilter
            self._spectral_prefilter = SpectralPreFilter(
                min_harmonic_ratio=self.config.min_harmonic_ratio,
            )

        logger.info(
            "clap_model_loaded",
            positive_labels=self.config.positive_labels,
            speech_labels=self.config.speech_labels,
            percussive_labels=self.config.percussive_labels,
            bird_labels=self.config.bird_labels,
            other_labels=self.config.other_labels,
            speech_veto_threshold=self.config.speech_veto_threshold,
            percussive_veto_threshold=self.config.percussive_veto_threshold,
            bird_veto_threshold=self.config.bird_veto_threshold,
            detection_cooldown_frames=self.config.detection_cooldown_frames,
            duration_validation_enabled=self.config.duration_validation_enabled,
            min_duration_ms=self.config.min_duration_ms,
            max_duration_ms=self.config.max_duration_ms,
            hpss_enabled=self.config.hpss_enabled,
            min_harmonic_ratio=self.config.min_harmonic_ratio,
            text_embeddings_cached=True,
            num_cached_labels=len(self._all_labels),
        )

    def _cache_text_embeddings(self) -> None:
        """Pre-compute and cache text embeddings for all labels.

        This is called once during load() and the embeddings are reused
        for every detect() call, avoiding redundant computation.
        """
        import torch

        if not self._model or not self._processor:
            raise RuntimeError("Model not loaded. Call load() first.")

        logger.debug("caching_text_embeddings", labels=self._all_labels)

        # Tokenize all labels
        text_inputs = self._processor(
            text=self._all_labels,
            return_tensors="pt",
            padding=True,
        )
        text_inputs = {k: v.to(self._device) for k, v in text_inputs.items()}

        # Compute text embeddings once
        with torch.no_grad():
            text_features = self._model.get_text_features(**text_inputs)
            # Normalize for cosine similarity
            self._cached_text_embeddings = text_features / text_features.norm(
                p=2, dim=-1, keepdim=True
            )

        logger.info(
            "text_embeddings_cached",
            shape=list(self._cached_text_embeddings.shape),
            num_labels=len(self._all_labels),
        )

    @property
    def is_loaded(self) -> bool:
        """Check if the model is loaded."""
        return self._model is not None and self._cached_text_embeddings is not None

    def detect(
        self,
        audio: np.ndarray,
        sample_rate: int = 48000,
    ) -> tuple[float, bool, dict[str, float]]:
        """Run bark detection on audio using cached text embeddings.

        Args:
            audio: Audio array of shape (samples,) or (channels, samples).
                   Should be float32 in range [-1, 1] or int16.
            sample_rate: Sample rate of the audio.

        Returns:
            Tuple of:
            - bark_probability: Probability that audio contains a dog bark (0-1)
            - is_barking: Whether bark probability exceeds threshold
            - label_scores: Dictionary of all label scores for debugging
        """
        import torch

        if not self.is_loaded:
            self.load()

        # Convert to mono if stereo
        if audio.ndim == 2:
            audio = audio.mean(axis=0)

        # Convert int16 to float32 if needed
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0

        # Ensure float32, 1D, and contiguous
        audio = np.ascontiguousarray(audio.flatten(), dtype=np.float32)

        # CLAP requires 48000 Hz - resample if needed
        target_sr = 48000
        if sample_rate != target_sr:
            import torchaudio.functional as F
            import torch as torch_resample
            audio_tensor = torch_resample.from_numpy(audio).unsqueeze(0)
            audio_resampled = F.resample(audio_tensor, sample_rate, target_sr)
            audio = audio_resampled.squeeze(0).numpy()
            sample_rate = target_sr

        # Process audio to get audio embeddings
        audio_inputs = self._processor(
            audios=audio,
            sampling_rate=sample_rate,
            return_tensors="pt",
        )
        audio_inputs = {k: v.to(self._device) for k, v in audio_inputs.items()}

        # Compute audio embeddings (text embeddings are cached)
        with torch.no_grad():
            audio_features = self._model.get_audio_features(**audio_inputs)
            # Normalize for cosine similarity
            audio_features = audio_features / audio_features.norm(p=2, dim=-1, keepdim=True)

            # Compute similarity with cached text embeddings
            # audio_features: (1, D), cached_text_embeddings: (N, D)
            logits = (audio_features @ self._cached_text_embeddings.T).squeeze(0)

            # Convert to probabilities via softmax
            probs = torch.softmax(logits * 100.0, dim=-1)  # Scale like CLAP does
            probs = probs.cpu().numpy()

        # Build label scores dictionary
        label_scores = {
            label: float(probs[i])
            for i, label in enumerate(self._all_labels)
        }

        # Sum probabilities for positive labels (bark-related)
        bark_prob = sum(
            label_scores.get(label, 0.0)
            for label in self.config.positive_labels
        )

        # Normalize if needed (scores should already sum to ~1)
        total = sum(label_scores.values())
        if total > 0:
            bark_prob = bark_prob / total

        # Check for speech veto - if any speech label is high, don't trigger bark
        max_speech_score = max(
            label_scores.get(label, 0.0)
            for label in self.config.speech_labels
        )
        speech_detected = max_speech_score >= self.config.speech_veto_threshold

        # Check for percussive veto - if any percussive label is high, don't trigger bark
        max_percussive_score = max(
            label_scores.get(label, 0.0)
            for label in self.config.percussive_labels
        )
        percussive_detected = max_percussive_score >= self.config.percussive_veto_threshold

        # Check for bird veto - if any bird label is high, don't trigger bark
        # Birds are commonly misclassified as dog barks
        max_bird_score = max(
            label_scores.get(label, 0.0)
            for label in self.config.bird_labels
        )
        bird_detected = max_bird_score >= self.config.bird_veto_threshold

        # Check confidence margin - bark must beat best non-bark by margin
        non_bark_labels = (
            self.config.speech_labels +
            self.config.percussive_labels +
            self.config.bird_labels +
            self.config.other_labels
        )
        best_non_bark_score = max(
            label_scores.get(label, 0.0)
            for label in non_bark_labels
        )
        # Get max individual positive label score for comparison
        max_positive_score = max(
            label_scores.get(label, 0.0)
            for label in self.config.positive_labels
        )
        margin_met = (max_positive_score - best_non_bark_score) >= self.config.confidence_margin

        # Check duration validation - reject events too short/long to be barks
        duration_valid = True
        duration_ms = 0.0
        if self._temporal_validator is not None:
            duration_valid, duration_ms = self._temporal_validator.validate(
                audio, sample_rate
            )
            # Add duration to label_scores for debugging/monitoring
            label_scores["_duration_ms"] = duration_ms
            label_scores["_duration_valid"] = 1.0 if duration_valid else 0.0

        # Check HPSS - reject predominantly percussive sounds (keyboard clicks)
        hpss_valid = True
        harmonic_ratio = 0.0
        if self._spectral_prefilter is not None:
            hpss_valid, harmonic_ratio = self._spectral_prefilter.is_harmonic(
                audio, sample_rate
            )
            # Add HPSS results to label_scores for debugging/monitoring
            label_scores["_harmonic_ratio"] = harmonic_ratio
            label_scores["_hpss_valid"] = 1.0 if hpss_valid else 0.0

        # Apply detection logic with speech, percussive, bird veto, margin, duration, and HPSS check
        # This is the "raw" detection before rolling window confirmation
        raw_detection = (
            bark_prob >= self.config.threshold
            and not speech_detected
            and not percussive_detected
            and not bird_detected
            and margin_met
            and duration_valid
            and hpss_valid
        )

        # Reset rolling window on strong non-bark detection
        # This prevents carryover from previous barks when user is clearly typing, speaking, or birds
        # Threshold is lower than veto threshold to ensure window gets reset on clear non-bark sounds
        strong_non_bark_threshold = 0.35
        should_reset_window = (
            max_percussive_score >= strong_non_bark_threshold
            or max_speech_score >= strong_non_bark_threshold
            or max_bird_score >= strong_non_bark_threshold
        )
        if should_reset_window and any(self._detection_window):
            if max_percussive_score >= strong_non_bark_threshold:
                reset_reason = "percussive"
            elif max_speech_score >= strong_non_bark_threshold:
                reset_reason = "speech"
            else:
                reset_reason = "bird"
            logger.debug(
                "rolling_window_reset_by_non_bark",
                reason=reset_reason,
                percussive_score=f"{max_percussive_score:.3f}",
                speech_score=f"{max_speech_score:.3f}",
                bird_score=f"{max_bird_score:.3f}",
                previous_window=list(self._detection_window),
            )
            self._detection_window.clear()

        # Add to rolling window and check for confirmation
        self._detection_window.append(raw_detection)
        positive_count = sum(self._detection_window)

        # High confidence detections bypass rolling window (bark_prob > 0.8 and raw passed all checks)
        # This ensures strong/brief barks aren't missed by rolling window smoothing
        high_confidence_bypass = raw_detection and bark_prob >= 0.8
        is_barking = (
            positive_count >= self.config.rolling_window_min_positives
            or high_confidence_bypass
        )

        # Apply cooldown to prevent rapid-fire detections from the SAME sound
        # High confidence detections (new distinct barks) bypass cooldown
        if is_barking:
            if self._cooldown_counter > 0 and not high_confidence_bypass:
                # Still in cooldown and not high confidence - suppress this one
                logger.debug(
                    "bark_suppressed_by_cooldown",
                    cooldown_remaining=self._cooldown_counter,
                    bark_prob=f"{bark_prob:.3f}",
                )
                is_barking = False
            else:
                # Either no cooldown or high confidence - this is a valid bark
                # Reset/start cooldown
                self._cooldown_counter = self.config.detection_cooldown_frames
                if high_confidence_bypass:
                    logger.debug(
                        "high_confidence_bark_detected",
                        bark_prob=f"{bark_prob:.3f}",
                        bypassed_cooldown=self._cooldown_counter > 0,
                    )
        else:
            # Decrement cooldown counter each frame when not barking
            if self._cooldown_counter > 0:
                self._cooldown_counter -= 1

        # Log when speech veto is applied
        if bark_prob >= self.config.threshold and speech_detected:
            top_speech = max(
                ((label, label_scores.get(label, 0.0)) for label in self.config.speech_labels),
                key=lambda x: x[1],
            )
            logger.debug(
                "bark_vetoed_by_speech",
                bark_prob=f"{bark_prob:.3f}",
                speech_label=top_speech[0],
                speech_score=f"{top_speech[1]:.3f}",
                threshold=self.config.speech_veto_threshold,
            )

        # Log when percussive veto is applied
        if bark_prob >= self.config.threshold and percussive_detected and not speech_detected:
            top_percussive = max(
                ((label, label_scores.get(label, 0.0)) for label in self.config.percussive_labels),
                key=lambda x: x[1],
            )
            logger.debug(
                "bark_vetoed_by_percussive",
                bark_prob=f"{bark_prob:.3f}",
                percussive_label=top_percussive[0],
                percussive_score=f"{top_percussive[1]:.3f}",
                threshold=self.config.percussive_veto_threshold,
            )

        # Log when bird veto is applied
        if (
            bark_prob >= self.config.threshold
            and bird_detected
            and not speech_detected
            and not percussive_detected
        ):
            top_bird = max(
                ((label, label_scores.get(label, 0.0)) for label in self.config.bird_labels),
                key=lambda x: x[1],
            )
            logger.debug(
                "bark_vetoed_by_bird",
                bark_prob=f"{bark_prob:.3f}",
                bird_label=top_bird[0],
                bird_score=f"{top_bird[1]:.3f}",
                threshold=self.config.bird_veto_threshold,
            )

        # Log when margin check fails
        if (
            bark_prob >= self.config.threshold
            and not speech_detected
            and not percussive_detected
            and not bird_detected
            and not margin_met
        ):
            logger.debug(
                "bark_vetoed_by_margin",
                bark_prob=f"{bark_prob:.3f}",
                max_positive_score=f"{max_positive_score:.3f}",
                best_non_bark_score=f"{best_non_bark_score:.3f}",
                actual_margin=f"{max_positive_score - best_non_bark_score:.3f}",
                required_margin=self.config.confidence_margin,
            )

        # Log when duration check fails (event too short/long)
        if (
            bark_prob >= self.config.threshold
            and not speech_detected
            and not percussive_detected
            and not bird_detected
            and margin_met
            and not duration_valid
        ):
            logger.debug(
                "bark_vetoed_by_duration",
                bark_prob=f"{bark_prob:.3f}",
                duration_ms=f"{duration_ms:.1f}",
                min_duration_ms=self.config.min_duration_ms,
                max_duration_ms=self.config.max_duration_ms,
            )

        # Log when HPSS check fails (sound is predominantly percussive)
        if (
            bark_prob >= self.config.threshold
            and not speech_detected
            and not percussive_detected
            and not bird_detected
            and margin_met
            and duration_valid
            and not hpss_valid
        ):
            logger.debug(
                "bark_vetoed_by_hpss",
                bark_prob=f"{bark_prob:.3f}",
                harmonic_ratio=f"{harmonic_ratio:.3f}",
                min_harmonic_ratio=self.config.min_harmonic_ratio,
            )

        # Log rolling window state when raw detection differs from final
        if raw_detection != is_barking:
            logger.debug(
                "rolling_window_state",
                raw_detection=raw_detection,
                is_barking=is_barking,
                window=list(self._detection_window),
                positive_count=positive_count,
                required=self.config.rolling_window_min_positives,
            )

        return bark_prob, is_barking, label_scores

    def reset_detection_window(self) -> None:
        """Reset the rolling detection window.

        Call this when starting a new audio stream or after a long pause
        to avoid stale detection history affecting new detections.
        """
        self._detection_window.clear()
        logger.debug("detection_window_reset")

    def detect_with_details(
        self,
        audio: np.ndarray,
        sample_rate: int = 48000,
    ) -> dict[str, Any]:
        """Run detection and return detailed results.

        Useful for debugging and understanding model decisions.
        """
        bark_prob, is_barking, label_scores = self.detect(audio, sample_rate)

        # Sort labels by score
        sorted_labels = sorted(
            label_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        return {
            "bark_probability": bark_prob,
            "is_barking": is_barking,
            "threshold": self.config.threshold,
            "top_label": sorted_labels[0][0] if sorted_labels else None,
            "top_score": sorted_labels[0][1] if sorted_labels else 0.0,
            "all_scores": dict(sorted_labels),
        }

    def get_audio_embedding(
        self,
        audio: np.ndarray,
        sample_rate: int = 48000,
    ) -> np.ndarray:
        """Extract the 512-dimensional CLAP audio embedding.

        This method extracts the normalized audio embedding vector that can be
        used for fingerprinting and similarity matching. The embedding is
        L2 normalized for cosine similarity comparisons.

        Args:
            audio: Audio array of shape (samples,) or (channels, samples).
                   Should be float32 in range [-1, 1] or int16.
            sample_rate: Sample rate of the audio.

        Returns:
            Normalized 512-dimensional embedding vector as numpy array.

        Raises:
            RuntimeError: If the model is not loaded.
        """
        import torch

        if not self.is_loaded:
            self.load()

        # Convert to mono if stereo
        if audio.ndim == 2:
            audio = audio.mean(axis=0)

        # Convert int16 to float32 if needed
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0

        # Ensure float32, 1D, and contiguous
        audio = np.ascontiguousarray(audio.flatten(), dtype=np.float32)

        # CLAP requires 48000 Hz - resample if needed
        target_sr = 48000
        if sample_rate != target_sr:
            import torchaudio.functional as F
            import torch as torch_resample
            audio_tensor = torch_resample.from_numpy(audio).unsqueeze(0)
            audio_resampled = F.resample(audio_tensor, sample_rate, target_sr)
            audio = audio_resampled.squeeze(0).numpy()
            sample_rate = target_sr

        # Process audio to get audio embeddings
        audio_inputs = self._processor(
            audios=audio,
            sampling_rate=sample_rate,
            return_tensors="pt",
        )
        audio_inputs = {k: v.to(self._device) for k, v in audio_inputs.items()}

        # Compute audio embeddings
        with torch.no_grad():
            audio_features = self._model.get_audio_features(**audio_inputs)
            # L2 normalize for cosine similarity
            audio_features = audio_features / audio_features.norm(p=2, dim=-1, keepdim=True)
            # Convert to numpy
            embedding = audio_features.squeeze(0).cpu().numpy()

        logger.debug(
            "audio_embedding_extracted",
            embedding_shape=embedding.shape,
            embedding_norm=float(np.linalg.norm(embedding)),
        )

        return embedding


def create_clap_detector(
    threshold: float = 0.6,
    device: str = "cpu",
) -> CLAPDetector:
    """Create a CLAP detector with common defaults.

    Args:
        threshold: Bark detection threshold (0-1).
        device: Device for inference ("cpu" or "cuda").

    Returns:
        Configured CLAPDetector instance (not yet loaded).
    """
    config = CLAPConfig(
        threshold=threshold,
        device=device,
    )
    return CLAPDetector(config)
