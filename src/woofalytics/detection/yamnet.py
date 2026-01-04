"""YAMNet pre-filter for bark detection pipeline.

This module provides a fast pre-filter using Google's YAMNet model to skip
expensive CLAP inference on audio that is clearly not dog-related.

YAMNet is a lightweight (~3.7M params) audio classifier trained on AudioSet
that predicts 521 classes including Dog (69) and Bark (70). By checking if
dog-related probabilities are below a threshold, we can skip CLAP inference
for ~30-40% of audio chunks.

Usage:
    gate = YAMNetGate(YAMNetConfig(threshold=0.05))
    if gate.load():
        if gate.is_dog_sound(audio, sample_rate=44100):
            # Proceed to CLAP inference
            pass
        else:
            # Skip CLAP - audio is not dog-related
            pass
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

# AudioSet class indices for dog-related sounds
DOG_CLASS = 69   # "Dog"
BARK_CLASS = 70  # "Bark"


@dataclass
class YAMNetConfig:
    """Configuration for YAMNet pre-filter gate."""

    threshold: float = 0.05
    """Minimum dog probability to pass audio to CLAP. Low to avoid missing barks."""

    dog_classes: list[int] = field(default_factory=lambda: [DOG_CLASS, BARK_CLASS])
    """AudioSet class indices to check for dog sounds."""

    device: str = "cpu"
    """Device for inference (YAMNet typically runs on CPU)."""


class YAMNetGate:
    """Fast pre-filter using YAMNet for bark detection.

    This gate uses Google's YAMNet model to quickly classify audio and
    determine if it potentially contains dog sounds. If the maximum
    probability across dog-related classes is below the threshold,
    the audio is skipped without running expensive CLAP inference.

    The gate follows the same pattern as VADGate for consistency:
    - is_dog_sound() returns True if audio should proceed to CLAP
    - Returns True on errors (fallback to CLAP for safety)
    - Tracks skip/pass statistics
    """

    def __init__(self, config: YAMNetConfig | None = None) -> None:
        """Initialize YAMNet gate.

        Args:
            config: Configuration for the gate. Uses defaults if None.
        """
        self.config = config or YAMNetConfig()
        self._model = None
        self._loaded = False
        self._skipped_count = 0
        self._passed_count = 0
        self._last_dog_prob = 0.0  # Last dog probability for monitoring

    def load(self) -> bool:
        """Load YAMNet from TensorFlow Hub.

        Returns:
            True if model loaded successfully, False otherwise.
        """
        try:
            import tensorflow_hub as hub

            logger.info("yamnet_loading", source="tfhub.dev/google/yamnet/1")
            self._model = hub.load("https://tfhub.dev/google/yamnet/1")
            self._loaded = True
            logger.info(
                "yamnet_loaded",
                threshold=self.config.threshold,
                dog_classes=self.config.dog_classes,
            )
            return True
        except Exception as e:
            logger.warning("yamnet_load_failed", error=str(e), error_type=type(e).__name__)
            return False

    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._loaded

    def is_dog_sound(self, audio: np.ndarray, sample_rate: int = 44100) -> bool:
        """Check if audio likely contains dog sounds.

        Args:
            audio: Audio array of shape (samples,) or (channels, samples).
                   Can be int16 or float32.
            sample_rate: Sample rate of the audio.

        Returns:
            True if audio should proceed to CLAP (dog probability >= threshold
            or on error). False if audio can be skipped.
        """
        if not self._loaded:
            return True  # Fallback: pass to CLAP

        try:
            audio_16k = self._preprocess(audio, sample_rate)
            scores, _, _ = self._model(audio_16k)
            dog_prob = self._get_dog_probability(scores.numpy())
            self._last_dog_prob = dog_prob  # Store for monitoring

            is_dog = dog_prob >= self.config.threshold
            if is_dog:
                self._passed_count += 1
            else:
                self._skipped_count += 1

            return is_dog
        except Exception as e:
            logger.warning("yamnet_inference_error", error=str(e), error_type=type(e).__name__)
            return True  # Fallback: pass to CLAP

    def _preprocess(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """Preprocess audio for YAMNet: resample to 16kHz mono float32.

        Args:
            audio: Audio array of shape (samples,) or (channels, samples).
            sample_rate: Current sample rate.

        Returns:
            Audio resampled to 16kHz mono float32 in range [-1, 1].
        """
        import torch
        import torchaudio.functional as F

        # Normalize int16 to float32 [-1, 1] BEFORE mono conversion
        # (mean on int16 produces float64, losing dtype info)
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        elif audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Convert to mono if stereo
        if audio.ndim == 2:
            audio = audio.mean(axis=0)

        # Resample to 16kHz if needed
        if sample_rate != 16000:
            tensor = torch.from_numpy(audio).unsqueeze(0)
            audio = F.resample(tensor, sample_rate, 16000).squeeze(0).numpy()

        return audio

    def _get_dog_probability(self, scores: np.ndarray) -> float:
        """Extract maximum dog-related probability from YAMNet scores.

        YAMNet outputs scores of shape (frames, 521), where each frame
        corresponds to a single time step of roughly 10ms of audio at 16kHz.
        Internally, the waveform is split into overlapping 25ms windows with
        10ms hops. We take the mean across all frames and then return the max
        probability across the configured dog-related classes.

        Args:
            scores: YAMNet output scores of shape (frames, 521).

        Returns:
            Maximum probability across dog-related classes.
        """
        # Average across frames for overall prediction
        mean_scores = scores.mean(axis=0)
        # Get max probability across dog-related classes
        dog_probs = [mean_scores[i] for i in self.config.dog_classes]
        return float(max(dog_probs)) if dog_probs else 0.0

    def reset_stats(self) -> None:
        """Reset skip/pass statistics."""
        self._skipped_count = 0
        self._passed_count = 0

    @property
    def stats(self) -> dict:
        """Get YAMNet gate statistics."""
        total = self._skipped_count + self._passed_count
        return {
            "skipped": self._skipped_count,
            "passed": self._passed_count,
            "total": total,
            "skip_rate": self._skipped_count / total if total > 0 else 0.0,
        }

    @property
    def last_dog_probability(self) -> float:
        """Get last measured dog probability."""
        return self._last_dog_prob

    @property
    def threshold(self) -> float:
        """Get dog probability threshold."""
        return self.config.threshold
