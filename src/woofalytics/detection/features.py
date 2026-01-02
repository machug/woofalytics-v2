"""Audio feature extraction for bark detection.

This module extracts Mel filterbank features from audio for use
with the bark detection model.
"""

from __future__ import annotations

import torch
import torchaudio
import torchaudio.transforms as T
import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class FeatureExtractor:
    """Extract Mel filterbank features for bark detection.

    The model expects 80-dimensional log Mel filterbank features
    extracted from 60ms windows of 16kHz audio.
    """

    def __init__(
        self,
        source_sample_rate: int = 44100,
        target_sample_rate: int = 16000,
        n_mels: int = 80,
        frame_length_ms: int = 25,
        frame_shift_ms: int = 10,
    ) -> None:
        """Initialize feature extractor.

        Args:
            source_sample_rate: Input audio sample rate.
            target_sample_rate: Sample rate expected by model.
            n_mels: Number of Mel filterbank bins.
            frame_length_ms: Frame length in milliseconds.
            frame_shift_ms: Frame shift (hop) in milliseconds.
        """
        self.source_sample_rate = source_sample_rate
        self.target_sample_rate = target_sample_rate
        self.n_mels = n_mels
        self.frame_length_ms = frame_length_ms
        self.frame_shift_ms = frame_shift_ms

        # Create resampler if needed
        self._resampler: T.Resample | None = None
        if source_sample_rate != target_sample_rate:
            self._resampler = T.Resample(
                orig_freq=source_sample_rate,
                new_freq=target_sample_rate,
            )

    def extract(self, audio: np.ndarray | torch.Tensor) -> torch.Tensor:
        """Extract Mel filterbank features from audio.

        Args:
            audio: Audio array of shape (channels, samples) or (samples,).
                  Can be numpy array or torch tensor.
                  Expected dtype is int16 or float32.

        Returns:
            Flattened feature tensor of shape (1, n_features).
            For the default model, this is (1, 480) = 6 frames * 80 mels.
        """
        # Convert to torch tensor if needed
        if isinstance(audio, np.ndarray):
            if audio.dtype == np.int16:
                audio = torch.from_numpy(audio.astype(np.float32))
                audio = audio / 32768.0  # Normalize int16 to [-1, 1]
            else:
                audio = torch.from_numpy(audio)

        # Ensure 2D: (channels, samples)
        if audio.dim() == 1:
            audio = audio.unsqueeze(0)

        # Average channels to mono if needed
        if audio.shape[0] > 1:
            audio = audio.mean(dim=0, keepdim=True)

        # Normalize if not already in [-1, 1] range
        if audio.abs().max() > 1.0:
            audio = audio / audio.abs().max()

        # Resample if needed
        if self._resampler is not None:
            audio = self._resampler(audio)

        # Extract Mel filterbank features using Kaldi-compatible API
        # This matches the original woofalytics implementation
        mel_features = torchaudio.compliance.kaldi.fbank(
            waveform=audio,
            num_mel_bins=self.n_mels,
            frame_length=self.frame_length_ms,
            frame_shift=self.frame_shift_ms,
            sample_frequency=float(self.target_sample_rate),
        )

        # Flatten to (1, n_features) for model input
        return mel_features.flatten().unsqueeze(0)

    def extract_from_int16(self, audio: np.ndarray) -> torch.Tensor:
        """Extract features from int16 audio array.

        Convenience method for the common case of int16 audio.

        Args:
            audio: Int16 audio array of shape (channels, samples) or (samples,).

        Returns:
            Flattened feature tensor of shape (1, n_features).
        """
        # Convert int16 to float and normalize
        audio_float = audio.astype(np.float32) / 32768.0
        return self.extract(audio_float)


def create_default_extractor(source_sample_rate: int = 44100) -> FeatureExtractor:
    """Create a feature extractor with default settings for the bark model.

    Args:
        source_sample_rate: Input audio sample rate.

    Returns:
        Configured FeatureExtractor instance.
    """
    return FeatureExtractor(
        source_sample_rate=source_sample_rate,
        target_sample_rate=16000,
        n_mels=80,
        frame_length_ms=25,
        frame_shift_ms=10,
    )
