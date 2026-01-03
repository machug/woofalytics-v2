"""CLAP-based zero-shot bark detection.

This module uses the CLAP (Contrastive Language-Audio Pretraining) model
for zero-shot audio classification. CLAP can distinguish between dog barks
and human speech without any fine-tuning.
"""

from __future__ import annotations

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

    # Other non-bark sounds
    other_labels: list[str] = field(default_factory=lambda: [
        "silence",
        "background noise",
        "music",
    ])

    # Threshold for bark detection (probability that it's a bark vs not)
    threshold: float = 0.5

    # If any speech label exceeds this, veto the bark detection
    speech_veto_threshold: float = 0.15

    # If any percussive label exceeds this, veto the bark detection
    percussive_veto_threshold: float = 0.20

    # Bark score must beat best non-bark label by this margin
    confidence_margin: float = 0.15

    # Device for inference
    device: str = "cpu"


class CLAPDetector:
    """Zero-shot bark detector using CLAP.

    CLAP computes similarity between audio and text descriptions,
    enabling classification without any training on bark data.
    """

    def __init__(self, config: CLAPConfig | None = None) -> None:
        """Initialize the CLAP detector.

        Args:
            config: Configuration for the detector. Uses defaults if None.
        """
        self.config = config or CLAPConfig()
        self._pipeline: Any = None
        self._all_labels: list[str] = []
        self._positive_indices: set[int] = set()
        self._speech_indices: set[int] = set()
        self._percussive_indices: set[int] = set()

    def load(self) -> None:
        """Load the CLAP model.

        This is separate from __init__ to allow lazy loading.
        """
        from transformers import pipeline

        logger.info(
            "loading_clap_model",
            model=self.config.model_name,
            device=self.config.device,
        )

        self._pipeline = pipeline(
            "zero-shot-audio-classification",
            model=self.config.model_name,
            device=self.config.device,
        )

        # Combine all labels: positive, speech (for veto), percussive (for veto), and other
        self._all_labels = (
            self.config.positive_labels +
            self.config.speech_labels +
            self.config.percussive_labels +
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

        logger.info(
            "clap_model_loaded",
            positive_labels=self.config.positive_labels,
            speech_labels=self.config.speech_labels,
            percussive_labels=self.config.percussive_labels,
            other_labels=self.config.other_labels,
            speech_veto_threshold=self.config.speech_veto_threshold,
            percussive_veto_threshold=self.config.percussive_veto_threshold,
        )

    @property
    def is_loaded(self) -> bool:
        """Check if the model is loaded."""
        return self._pipeline is not None

    def detect(
        self,
        audio: np.ndarray,
        sample_rate: int = 48000,
    ) -> tuple[float, bool, dict[str, float]]:
        """Run bark detection on audio.

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
        if not self.is_loaded:
            self.load()

        # Convert to mono if stereo
        if audio.ndim == 2:
            audio = audio.mean(axis=0)

        # Convert int16 to float32 if needed
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0

        # Ensure float32, 1D, and contiguous (required by transformers pipeline)
        # The pipeline expects shape (n,) with float32 values
        audio = np.ascontiguousarray(audio.flatten(), dtype=np.float32)

        # Run classification - pass audio array directly as shown in HF docs example:
        # classifier(audio, candidate_labels=["Sound of a dog", ...])
        results = self._pipeline(
            audio,
            candidate_labels=self._all_labels,
        )

        # Parse results - pipeline returns list of {score, label} dicts
        label_scores = {r["label"]: r["score"] for r in results}

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

        # Check confidence margin - bark must beat best non-bark by margin
        non_bark_labels = (
            self.config.speech_labels +
            self.config.percussive_labels +
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

        # Apply detection logic with speech, percussive veto, and margin check
        is_barking = (
            bark_prob >= self.config.threshold
            and not speech_detected
            and not percussive_detected
            and margin_met
        )

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

        # Log when margin check fails
        if (
            bark_prob >= self.config.threshold
            and not speech_detected
            and not percussive_detected
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

        return bark_prob, is_barking, label_scores

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
