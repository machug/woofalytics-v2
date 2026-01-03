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

        # Cached text embeddings - computed once on load()
        self._cached_text_embeddings: Any = None

    def load(self) -> None:
        """Load the CLAP model and pre-compute text embeddings.

        This is separate from __init__ to allow lazy loading.
        Text embeddings are computed once and cached for all future
        detect() calls, significantly reducing inference time.
        """
        import torch
        from transformers import ClapModel, ClapProcessor

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

        # Combine all labels: positive, speech (for veto), and other
        self._all_labels = (
            self.config.positive_labels +
            self.config.speech_labels +
            self.config.other_labels
        )
        self._positive_indices = set(range(len(self.config.positive_labels)))

        # Track speech label indices for veto logic
        speech_start = len(self.config.positive_labels)
        speech_end = speech_start + len(self.config.speech_labels)
        self._speech_indices = set(range(speech_start, speech_end))

        # Pre-compute and cache text embeddings for all labels
        self._cache_text_embeddings()

        logger.info(
            "clap_model_loaded",
            positive_labels=self.config.positive_labels,
            speech_labels=self.config.speech_labels,
            other_labels=self.config.other_labels,
            speech_veto_threshold=self.config.speech_veto_threshold,
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

        # Apply detection logic with speech veto
        is_barking = bark_prob >= self.config.threshold and not speech_detected

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
