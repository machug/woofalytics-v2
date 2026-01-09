"""Tests for audio resampling cache."""

from __future__ import annotations

import numpy as np
import pytest

from woofalytics.detection.resample_cache import AudioResampleCache


class TestAudioResampleCache:
    """Tests for AudioResampleCache class."""

    def test_initialization(self):
        """Test cache initialization."""
        cache = AudioResampleCache()

        assert cache._cache == {}
        assert cache._source_rate is None
        assert cache.stats["hits"] == 0
        assert cache.stats["misses"] == 0

    def test_no_resampling_needed(self):
        """Test when source and target rate are the same."""
        cache = AudioResampleCache()

        audio = np.random.randn(44100).astype(np.float32)
        result = cache.get_resampled(audio, source_rate=44100, target_rate=44100)

        # Should return same array without caching
        assert result is audio
        assert 44100 not in cache._cache

    def test_resampling_and_caching(self):
        """Test resampling and caching behavior."""
        cache = AudioResampleCache()

        audio = np.random.randn(44100).astype(np.float32)

        # First call should resample and cache
        result1 = cache.get_resampled(audio, source_rate=44100, target_rate=16000)

        assert 16000 in cache._cache
        assert len(result1) == 16000
        assert cache.stats["misses"] == 1
        assert cache.stats["hits"] == 0

        # Second call should return cached result
        result2 = cache.get_resampled(audio, source_rate=44100, target_rate=16000)

        assert result2 is result1  # Same object from cache
        assert cache.stats["misses"] == 1
        assert cache.stats["hits"] == 1

    def test_multiple_target_rates(self):
        """Test caching multiple target rates."""
        cache = AudioResampleCache()

        audio = np.random.randn(44100).astype(np.float32)

        # Resample to 16kHz
        result_16k = cache.get_resampled(audio, source_rate=44100, target_rate=16000)
        assert len(result_16k) == 16000

        # Resample to 48kHz
        result_48k = cache.get_resampled(audio, source_rate=44100, target_rate=48000)
        assert len(result_48k) == 48000

        # Both should be cached
        assert 16000 in cache._cache
        assert 48000 in cache._cache
        assert cache.stats["misses"] == 2

    def test_clear(self):
        """Test clearing the cache."""
        cache = AudioResampleCache()

        audio = np.random.randn(44100).astype(np.float32)
        cache.get_resampled(audio, source_rate=44100, target_rate=16000)

        assert 16000 in cache._cache
        assert cache._source_rate == 44100

        cache.clear()

        assert cache._cache == {}
        assert cache._source_rate is None

    def test_source_rate_change_clears_cache(self):
        """Test that changing source rate clears the cache."""
        cache = AudioResampleCache()

        # First audio at 44100 Hz
        audio1 = np.random.randn(44100).astype(np.float32)
        result1 = cache.get_resampled(audio1, source_rate=44100, target_rate=16000)
        assert cache._source_rate == 44100

        # New audio at 48000 Hz - should clear cache
        audio2 = np.random.randn(48000).astype(np.float32)
        result2 = cache.get_resampled(audio2, source_rate=48000, target_rate=16000)

        assert cache._source_rate == 48000
        # The 16kHz entry should be new (from audio2, not audio1)
        assert 16000 in cache._cache

    def test_stereo_audio(self):
        """Test resampling stereo audio."""
        cache = AudioResampleCache()

        # Stereo audio (2, samples)
        audio = np.random.randn(2, 44100).astype(np.float32)
        result = cache.get_resampled(audio, source_rate=44100, target_rate=16000)

        # Should maintain stereo shape
        assert result.shape == (2, 16000)

    def test_hit_rate(self):
        """Test hit rate calculation."""
        cache = AudioResampleCache()

        audio = np.random.randn(44100).astype(np.float32)

        # 1 miss
        cache.get_resampled(audio, source_rate=44100, target_rate=16000)
        # 3 hits
        cache.get_resampled(audio, source_rate=44100, target_rate=16000)
        cache.get_resampled(audio, source_rate=44100, target_rate=16000)
        cache.get_resampled(audio, source_rate=44100, target_rate=16000)

        stats = cache.stats
        assert stats["hits"] == 3
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.75

    def test_reset_stats(self):
        """Test resetting statistics."""
        cache = AudioResampleCache()

        audio = np.random.randn(44100).astype(np.float32)
        cache.get_resampled(audio, source_rate=44100, target_rate=16000)
        cache.get_resampled(audio, source_rate=44100, target_rate=16000)

        assert cache.stats["hits"] == 1
        assert cache.stats["misses"] == 1

        cache.reset_stats()

        assert cache.stats["hits"] == 0
        assert cache.stats["misses"] == 0
        # Cache itself should still have the data
        assert 16000 in cache._cache

    def test_cached_rates_in_stats(self):
        """Test that cached rates are reported in stats."""
        cache = AudioResampleCache()

        audio = np.random.randn(44100).astype(np.float32)
        cache.get_resampled(audio, source_rate=44100, target_rate=16000)
        cache.get_resampled(audio, source_rate=44100, target_rate=48000)
        cache.get_resampled(audio, source_rate=44100, target_rate=22050)

        assert set(cache.stats["cached_rates"]) == {16000, 48000, 22050}
