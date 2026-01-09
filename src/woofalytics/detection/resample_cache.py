"""Audio resampling cache to eliminate redundant conversions.

This module provides a cache for resampled audio to avoid redundant
sample rate conversions when the same audio is processed by multiple
models that share the same target sample rate.

Performance context:
- VAD: No resampling (works on source rate)
- YAMNet: Needs 16kHz
- CLAP: Needs 48kHz
- HPSS (spectral filter): Needs 22050Hz
- Legacy MLP: Needs 16kHz

Without caching, the same 16kHz conversion happens for both YAMNet
and legacy MLP. This cache eliminates those redundant conversions.
"""

from __future__ import annotations

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class AudioResampleCache:
    """Cache resampled audio to avoid redundant conversions.

    This cache stores resampled audio by target sample rate. When a new
    audio frame is processed, call clear() first to reset the cache,
    then use get_resampled() for each model's required sample rate.

    The cache automatically clears itself if the source rate changes,
    which handles edge cases where audio configuration changes mid-stream.

    Usage:
        cache = AudioResampleCache()

        # At the start of each audio frame processing:
        cache.clear()

        # For each model that needs resampled audio:
        audio_16k = cache.get_resampled(audio, source_rate=44100, target_rate=16000)
        audio_48k = cache.get_resampled(audio, source_rate=44100, target_rate=48000)

        # Second call to 16kHz returns cached result (no resampling):
        audio_16k_again = cache.get_resampled(audio, source_rate=44100, target_rate=16000)
    """

    def __init__(self) -> None:
        """Initialize the cache."""
        self._cache: dict[int, np.ndarray] = {}
        self._source_rate: int | None = None
        self._hit_count: int = 0
        self._miss_count: int = 0

    def clear(self) -> None:
        """Clear cache for new audio frame.

        Call this at the start of each audio frame processing to ensure
        stale resampled audio from previous frames is not used.
        """
        self._cache.clear()
        self._source_rate = None

    def get_resampled(
        self,
        audio: np.ndarray,
        source_rate: int,
        target_rate: int,
    ) -> np.ndarray:
        """Get resampled audio, using cache if available.

        Args:
            audio: Audio array of shape (samples,) or (channels, samples).
                   Should be float32 in range [-1, 1].
            source_rate: Original sample rate of the audio.
            target_rate: Desired sample rate.

        Returns:
            Audio resampled to target_rate. If target_rate == source_rate,
            returns the original audio unchanged.

        Note:
            The audio should be converted to mono and normalized to float32
            before calling this method. The cache assumes consistent input
            format within a single frame.
        """
        # Auto-clear if source rate changed (handles config changes)
        if source_rate != self._source_rate:
            if self._source_rate is not None:
                logger.debug(
                    "resample_cache_source_rate_changed",
                    old_rate=self._source_rate,
                    new_rate=source_rate,
                )
            self.clear()
            self._source_rate = source_rate

        # No resampling needed
        if target_rate == source_rate:
            return audio

        # Check cache
        if target_rate in self._cache:
            self._hit_count += 1
            return self._cache[target_rate]

        # Cache miss - do the actual resampling
        self._miss_count += 1

        import torch
        import torchaudio.functional as F

        # Ensure audio is the right shape for resampling
        # torchaudio expects (channels, samples) or (batch, channels, samples)
        if audio.ndim == 1:
            audio_tensor = torch.from_numpy(audio).unsqueeze(0)
        else:
            audio_tensor = torch.from_numpy(audio)

        # Resample
        resampled_tensor = F.resample(audio_tensor, source_rate, target_rate)

        # Convert back to numpy, preserving original shape
        if audio.ndim == 1:
            resampled = resampled_tensor.squeeze(0).numpy()
        else:
            resampled = resampled_tensor.numpy()

        # Store in cache
        self._cache[target_rate] = resampled

        # Log cache stats periodically
        total = self._hit_count + self._miss_count
        if total > 0 and total % 100 == 0:
            hit_rate = self._hit_count / total * 100
            logger.debug(
                "resample_cache_stats",
                hits=self._hit_count,
                misses=self._miss_count,
                hit_rate=f"{hit_rate:.1f}%",
                cached_rates=list(self._cache.keys()),
            )

        return resampled

    @property
    def stats(self) -> dict:
        """Get cache statistics."""
        total = self._hit_count + self._miss_count
        return {
            "hits": self._hit_count,
            "misses": self._miss_count,
            "hit_rate": self._hit_count / total if total > 0 else 0.0,
            "cached_rates": list(self._cache.keys()),
        }

    def reset_stats(self) -> None:
        """Reset hit/miss statistics."""
        self._hit_count = 0
        self._miss_count = 0
