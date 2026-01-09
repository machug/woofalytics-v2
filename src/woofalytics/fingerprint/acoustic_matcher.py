"""Secondary matching using acoustic features.

This module provides similarity comparison between barks using
interpretable acoustic features extracted from audio segments.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import structlog

from woofalytics.fingerprint.acoustic_features import AcousticFeatures

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = structlog.get_logger(__name__)


@dataclass
class FeatureWeights:
    """Weights for combining acoustic feature similarities.

    Each weight determines the contribution of that feature
    to the overall similarity score. Weights should sum to 1.0.
    """

    duration: float = 0.10
    pitch: float = 0.20
    spectral_centroid: float = 0.15
    spectral_rolloff: float = 0.10
    spectral_bandwidth: float = 0.10
    zero_crossing_rate: float = 0.05
    mfcc: float = 0.25
    energy: float = 0.05

    def __post_init__(self) -> None:
        """Verify weights sum to approximately 1.0."""
        total = (
            self.duration
            + self.pitch
            + self.spectral_centroid
            + self.spectral_rolloff
            + self.spectral_bandwidth
            + self.zero_crossing_rate
            + self.mfcc
            + self.energy
        )
        if not 0.99 <= total <= 1.01:
            logger.warning("feature_weights_not_normalized", total=total)


class AcousticMatcher:
    """Compare acoustic features between bark segments.

    Uses a weighted combination of feature similarities to compute
    an overall acoustic similarity score between two barks.
    """

    # Reference ranges for normalization
    # These are typical ranges observed in dog barks
    DURATION_RANGE_MS = (50.0, 500.0)  # 50ms to 500ms
    PITCH_RANGE_HZ = (100.0, 1500.0)  # 100Hz to 1500Hz
    CENTROID_RANGE_HZ = (500.0, 5000.0)  # 500Hz to 5000Hz
    ROLLOFF_RANGE_HZ = (1000.0, 10000.0)  # 1kHz to 10kHz
    BANDWIDTH_RANGE_HZ = (500.0, 3000.0)  # 500Hz to 3000Hz
    ZCR_RANGE = (0.0, 0.3)  # 0 to 0.3 crossings per sample
    ENERGY_RANGE_DB = (-40.0, 0.0)  # -40dB to 0dB

    def __init__(
        self,
        weights: FeatureWeights | None = None,
    ) -> None:
        """Initialize the acoustic matcher.

        Args:
            weights: Feature weights for similarity computation.
                    Uses default weights if not provided.
        """
        self.weights = weights or FeatureWeights()
        self._log = logger.bind(component="acoustic_matcher")

    def compute_similarity(
        self, features1: AcousticFeatures, features2: AcousticFeatures
    ) -> float:
        """Compute overall acoustic similarity between two barks.

        Args:
            features1: Acoustic features of first bark.
            features2: Acoustic features of second bark.

        Returns:
            Similarity score from 0.0 (completely different) to 1.0 (identical).
        """
        similarities: dict[str, float] = {}
        total_weight = 0.0
        weighted_sum = 0.0

        # Duration similarity
        sim = self._scalar_similarity(
            features1.duration_ms,
            features2.duration_ms,
            self.DURATION_RANGE_MS[0],
            self.DURATION_RANGE_MS[1],
        )
        similarities["duration"] = sim
        weighted_sum += sim * self.weights.duration
        total_weight += self.weights.duration

        # Pitch similarity (handle None values)
        if features1.pitch_hz is not None and features2.pitch_hz is not None:
            sim = self._scalar_similarity(
                features1.pitch_hz,
                features2.pitch_hz,
                self.PITCH_RANGE_HZ[0],
                self.PITCH_RANGE_HZ[1],
            )
            similarities["pitch"] = sim
            weighted_sum += sim * self.weights.pitch
            total_weight += self.weights.pitch
        elif features1.pitch_hz is None and features2.pitch_hz is None:
            # Both unvoiced/undetected - consider similar
            similarities["pitch"] = 0.8
            weighted_sum += 0.8 * self.weights.pitch
            total_weight += self.weights.pitch
        else:
            # One has pitch, one doesn't - low similarity
            similarities["pitch"] = 0.2
            weighted_sum += 0.2 * self.weights.pitch
            total_weight += self.weights.pitch

        # Spectral centroid similarity
        sim = self._scalar_similarity(
            features1.spectral_centroid_hz,
            features2.spectral_centroid_hz,
            self.CENTROID_RANGE_HZ[0],
            self.CENTROID_RANGE_HZ[1],
        )
        similarities["centroid"] = sim
        weighted_sum += sim * self.weights.spectral_centroid
        total_weight += self.weights.spectral_centroid

        # Spectral rolloff similarity
        sim = self._scalar_similarity(
            features1.spectral_rolloff_hz,
            features2.spectral_rolloff_hz,
            self.ROLLOFF_RANGE_HZ[0],
            self.ROLLOFF_RANGE_HZ[1],
        )
        similarities["rolloff"] = sim
        weighted_sum += sim * self.weights.spectral_rolloff
        total_weight += self.weights.spectral_rolloff

        # Spectral bandwidth similarity
        sim = self._scalar_similarity(
            features1.spectral_bandwidth_hz,
            features2.spectral_bandwidth_hz,
            self.BANDWIDTH_RANGE_HZ[0],
            self.BANDWIDTH_RANGE_HZ[1],
        )
        similarities["bandwidth"] = sim
        weighted_sum += sim * self.weights.spectral_bandwidth
        total_weight += self.weights.spectral_bandwidth

        # Zero-crossing rate similarity
        sim = self._scalar_similarity(
            features1.zero_crossing_rate,
            features2.zero_crossing_rate,
            self.ZCR_RANGE[0],
            self.ZCR_RANGE[1],
        )
        similarities["zcr"] = sim
        weighted_sum += sim * self.weights.zero_crossing_rate
        total_weight += self.weights.zero_crossing_rate

        # MFCC similarity (cosine similarity of mean vectors)
        sim = self._mfcc_similarity(features1.mfcc_mean, features2.mfcc_mean)
        similarities["mfcc"] = sim
        weighted_sum += sim * self.weights.mfcc
        total_weight += self.weights.mfcc

        # Energy similarity
        sim = self._scalar_similarity(
            features1.energy_db,
            features2.energy_db,
            self.ENERGY_RANGE_DB[0],
            self.ENERGY_RANGE_DB[1],
        )
        similarities["energy"] = sim
        weighted_sum += sim * self.weights.energy
        total_weight += self.weights.energy

        # Compute final weighted similarity
        overall = weighted_sum / total_weight if total_weight > 0 else 0.0

        self._log.debug(
            "similarity_computed",
            overall=round(overall, 3),
            components=similarities,
        )

        return overall

    def _scalar_similarity(
        self, val1: float, val2: float, min_val: float, max_val: float
    ) -> float:
        """Compute similarity between two scalar values.

        Uses normalized absolute difference, where closer values
        give higher similarity.

        Args:
            val1: First value.
            val2: Second value.
            min_val: Minimum expected value (for normalization).
            max_val: Maximum expected value (for normalization).

        Returns:
            Similarity from 0.0 to 1.0.
        """
        range_val = max_val - min_val
        if range_val <= 0:
            return 1.0 if val1 == val2 else 0.0

        # Normalize difference by range
        diff = abs(val1 - val2) / range_val

        # Convert difference to similarity (exponential decay)
        # diff=0 -> sim=1.0, diff=1 -> sim~0.37, diff=2 -> sim~0.14
        similarity = np.exp(-diff * 2.0)

        return float(similarity)

    def _mfcc_similarity(
        self, mfcc1: NDArray[np.floating], mfcc2: NDArray[np.floating]
    ) -> float:
        """Compute cosine similarity between MFCC vectors.

        Args:
            mfcc1: First MFCC mean vector (13,).
            mfcc2: Second MFCC mean vector (13,).

        Returns:
            Cosine similarity from -1.0 to 1.0, normalized to 0.0-1.0.
        """
        # Handle zero vectors
        norm1 = np.linalg.norm(mfcc1)
        norm2 = np.linalg.norm(mfcc2)

        if norm1 < 1e-10 or norm2 < 1e-10:
            # If both are zero, they're similar; if one is zero, they're different
            if norm1 < 1e-10 and norm2 < 1e-10:
                return 1.0
            return 0.0

        # Cosine similarity: dot(a,b) / (|a| * |b|)
        cosine_sim = np.dot(mfcc1, mfcc2) / (norm1 * norm2)

        # Normalize from [-1, 1] to [0, 1]
        normalized = (cosine_sim + 1.0) / 2.0

        return float(normalized)


def create_acoustic_matcher(weights: FeatureWeights | None = None) -> AcousticMatcher:
    """Create an acoustic matcher with optional custom weights.

    Args:
        weights: Feature weights for similarity computation.
                Uses default weights if not provided.

    Returns:
        Configured AcousticMatcher instance.
    """
    return AcousticMatcher(weights=weights)
