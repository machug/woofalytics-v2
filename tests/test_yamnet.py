"""Tests for YAMNet pre-filter module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from woofalytics.detection.yamnet import (
    BARK_CLASS,
    DOG_CLASS,
    YAMNetConfig,
    YAMNetGate,
)


class TestYAMNetConfig:
    """Tests for YAMNetConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = YAMNetConfig()

        assert config.threshold == 0.05
        assert config.dog_classes == [DOG_CLASS, BARK_CLASS]
        assert config.device == "cpu"

    def test_custom_values(self):
        """Test custom configuration values."""
        config = YAMNetConfig(
            threshold=0.10,
            dog_classes=[69, 70, 71],
            device="cuda",
        )

        assert config.threshold == 0.10
        assert config.dog_classes == [69, 70, 71]
        assert config.device == "cuda"


class TestYAMNetGate:
    """Tests for YAMNetGate class."""

    def test_initialization(self):
        """Test gate initialization with default config."""
        gate = YAMNetGate()

        assert gate.config.threshold == 0.05
        assert not gate.is_loaded
        assert gate.stats["skipped"] == 0
        assert gate.stats["passed"] == 0

    def test_initialization_with_config(self):
        """Test gate initialization with custom config."""
        config = YAMNetConfig(threshold=0.10)
        gate = YAMNetGate(config)

        assert gate.config.threshold == 0.10

    def test_is_dog_sound_returns_true_when_not_loaded(self):
        """Test fallback behavior when model not loaded."""
        gate = YAMNetGate()
        audio = np.random.randn(1000).astype(np.float32)

        # Should return True (pass to CLAP) when model not loaded
        result = gate.is_dog_sound(audio, sample_rate=44100)

        assert result is True

    def test_load_success(self):
        """Test successful model loading."""
        with patch.dict("sys.modules", {"tensorflow_hub": MagicMock()}):
            import sys
            mock_hub = sys.modules["tensorflow_hub"]
            mock_model = MagicMock()
            mock_hub.load.return_value = mock_model

            gate = YAMNetGate()
            result = gate.load()

            assert result is True
            assert gate.is_loaded
            mock_hub.load.assert_called_once_with("https://tfhub.dev/google/yamnet/1")

    def test_load_failure(self):
        """Test model loading failure."""
        with patch.dict("sys.modules", {"tensorflow_hub": MagicMock()}):
            import sys
            mock_hub = sys.modules["tensorflow_hub"]
            mock_hub.load.side_effect = Exception("Network error")

            gate = YAMNetGate()
            result = gate.load()

            assert result is False
            assert not gate.is_loaded

    def test_is_dog_sound_above_threshold(self):
        """Test detection when dog probability is above threshold."""
        with patch.dict("sys.modules", {"tensorflow_hub": MagicMock()}):
            import sys
            mock_hub = sys.modules["tensorflow_hub"]

            # Setup mock model
            mock_model = MagicMock()
            mock_hub.load.return_value = mock_model

            # Create scores with high dog probability (class 69 and 70)
            scores = np.zeros((5, 521))
            scores[:, DOG_CLASS] = 0.3  # 30% dog probability
            scores[:, BARK_CLASS] = 0.2  # 20% bark probability

            # Mock tensor with .numpy() method
            mock_scores = MagicMock()
            mock_scores.numpy.return_value = scores
            mock_model.return_value = (mock_scores, None, None)

            gate = YAMNetGate(YAMNetConfig(threshold=0.05))
            gate.load()

            audio = np.random.randn(16000).astype(np.float32)
            result = gate.is_dog_sound(audio, sample_rate=16000)

            assert result is True
            assert gate.stats["passed"] == 1
            assert gate.stats["skipped"] == 0

    def test_is_dog_sound_below_threshold(self):
        """Test detection when dog probability is below threshold."""
        with patch.dict("sys.modules", {"tensorflow_hub": MagicMock()}):
            import sys
            mock_hub = sys.modules["tensorflow_hub"]

            # Setup mock model
            mock_model = MagicMock()
            mock_hub.load.return_value = mock_model

            # Create scores with low dog probability
            scores = np.zeros((5, 521))
            scores[:, DOG_CLASS] = 0.01  # 1% dog probability
            scores[:, BARK_CLASS] = 0.01  # 1% bark probability

            # Mock tensor with .numpy() method
            mock_scores = MagicMock()
            mock_scores.numpy.return_value = scores
            mock_model.return_value = (mock_scores, None, None)

            gate = YAMNetGate(YAMNetConfig(threshold=0.05))
            gate.load()

            audio = np.random.randn(16000).astype(np.float32)
            result = gate.is_dog_sound(audio, sample_rate=16000)

            assert result is False
            assert gate.stats["passed"] == 0
            assert gate.stats["skipped"] == 1

    def test_is_dog_sound_inference_error_fallback(self):
        """Test fallback to CLAP on inference error."""
        with patch.dict("sys.modules", {"tensorflow_hub": MagicMock()}):
            import sys
            mock_hub = sys.modules["tensorflow_hub"]

            # Setup mock model that raises error
            mock_model = MagicMock()
            mock_model.side_effect = Exception("Inference error")
            mock_hub.load.return_value = mock_model

            gate = YAMNetGate()
            gate.load()

            audio = np.random.randn(16000).astype(np.float32)
            result = gate.is_dog_sound(audio, sample_rate=16000)

            # Should return True (fallback to CLAP) on error
            assert result is True

    def test_preprocess_mono_float32(self):
        """Test preprocessing with mono float32 audio."""
        gate = YAMNetGate()

        audio = np.random.randn(44100).astype(np.float32)
        result = gate._preprocess(audio, sample_rate=44100)

        # Should resample from 44100 to 16000
        expected_length = int(44100 * 16000 / 44100)
        assert len(result) == expected_length
        assert result.dtype == np.float32

    def test_preprocess_stereo_int16(self):
        """Test preprocessing with stereo int16 audio."""
        gate = YAMNetGate()

        # Stereo int16 audio (channels, samples)
        audio = np.random.randint(-32768, 32767, (2, 44100), dtype=np.int16)
        result = gate._preprocess(audio, sample_rate=44100)

        # Should be mono, float32, resampled to 16kHz
        # Note: torchaudio resampling may produce slightly different length
        assert result.ndim == 1
        assert len(result) == 16000  # 44100 -> 16000 should be exact
        assert result.dtype == np.float32
        assert np.abs(result).max() <= 1.0  # Normalized to [-1, 1]

    def test_preprocess_already_16khz(self):
        """Test preprocessing with audio already at 16kHz."""
        gate = YAMNetGate()

        audio = np.random.randn(16000).astype(np.float32)
        result = gate._preprocess(audio, sample_rate=16000)

        # Should not resample
        assert len(result) == 16000

    def test_get_dog_probability(self):
        """Test extracting dog probability from scores."""
        gate = YAMNetGate(YAMNetConfig(dog_classes=[69, 70]))

        # Scores with different probabilities per frame
        scores = np.zeros((3, 521))
        scores[0, DOG_CLASS] = 0.3
        scores[1, DOG_CLASS] = 0.4
        scores[2, DOG_CLASS] = 0.2
        scores[0, BARK_CLASS] = 0.1
        scores[1, BARK_CLASS] = 0.2
        scores[2, BARK_CLASS] = 0.3

        prob = gate._get_dog_probability(scores)

        # Should return max of mean probabilities
        expected_dog_mean = (0.3 + 0.4 + 0.2) / 3  # 0.3
        expected_bark_mean = (0.1 + 0.2 + 0.3) / 3  # 0.2
        expected = max(expected_dog_mean, expected_bark_mean)

        assert abs(prob - expected) < 0.001

    def test_stats_property(self):
        """Test statistics tracking."""
        gate = YAMNetGate()
        gate._skipped_count = 30
        gate._passed_count = 70

        stats = gate.stats

        assert stats["skipped"] == 30
        assert stats["passed"] == 70
        assert stats["total"] == 100
        assert stats["skip_rate"] == 0.3

    def test_stats_empty(self):
        """Test statistics when no inferences performed."""
        gate = YAMNetGate()

        stats = gate.stats

        assert stats["skipped"] == 0
        assert stats["passed"] == 0
        assert stats["total"] == 0
        assert stats["skip_rate"] == 0.0

    def test_reset_stats(self):
        """Test statistics reset."""
        gate = YAMNetGate()
        gate._skipped_count = 50
        gate._passed_count = 50

        gate.reset_stats()

        assert gate.stats["skipped"] == 0
        assert gate.stats["passed"] == 0


class TestYAMNetConstants:
    """Tests for module constants."""

    def test_dog_class_index(self):
        """Test DOG_CLASS constant matches AudioSet index."""
        assert DOG_CLASS == 69

    def test_bark_class_index(self):
        """Test BARK_CLASS constant matches AudioSet index."""
        assert BARK_CLASS == 70
