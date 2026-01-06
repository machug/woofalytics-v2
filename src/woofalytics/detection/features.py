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


class TemporalValidator:
    """Validate audio events based on temporal duration.

    Rejects events that are too short (keyboard clicks ~10-50ms) or too long
    to be real dog barks. Dog barks typically range from 100-1500ms.

    Uses the amplitude envelope to measure the duration of sound events,
    from onset (when energy rises above threshold) to offset (when it falls below).
    """

    def __init__(
        self,
        min_duration_ms: float = 80,
        max_duration_ms: float = 1500,
        onset_threshold: float = 0.1,
        offset_threshold: float = 0.05,
    ) -> None:
        """Initialize temporal validator.

        Args:
            min_duration_ms: Minimum event duration in milliseconds.
                             Keyboard clicks are 10-50ms, barks are 100ms+.
            max_duration_ms: Maximum event duration in milliseconds.
                             Very long sounds are unlikely to be single barks.
            onset_threshold: Amplitude threshold (0-1) for detecting event start.
            offset_threshold: Amplitude threshold (0-1) for detecting event end.
        """
        self.min_duration_ms = min_duration_ms
        self.max_duration_ms = max_duration_ms
        self.onset_threshold = onset_threshold
        self.offset_threshold = offset_threshold

    def validate(
        self,
        audio: np.ndarray,
        sample_rate: int,
    ) -> tuple[bool, float]:
        """Validate audio event duration.

        Args:
            audio: Audio array of shape (samples,) or (channels, samples).
                   Should be float32 in range [-1, 1] or int16.
            sample_rate: Sample rate of the audio.

        Returns:
            Tuple of:
            - is_valid: True if duration is within acceptable range
            - duration_ms: Measured event duration in milliseconds
        """
        # Convert to mono if stereo
        if audio.ndim == 2:
            audio = audio.mean(axis=0)

        # Convert int16 to float32 if needed
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0

        # Extract amplitude envelope using Hilbert transform
        envelope = self._extract_envelope(audio)

        # Normalize envelope to 0-1 range
        max_amp = envelope.max()
        if max_amp > 0:
            envelope = envelope / max_amp

        # Measure duration from onset to offset
        duration_samples = self._measure_duration(envelope)
        duration_ms = (duration_samples / sample_rate) * 1000.0

        # Validate against thresholds
        is_valid = self.min_duration_ms <= duration_ms <= self.max_duration_ms

        return is_valid, duration_ms

    def _extract_envelope(self, audio: np.ndarray) -> np.ndarray:
        """Extract amplitude envelope using Hilbert transform.

        The Hilbert transform gives us the analytic signal, whose absolute
        value is the instantaneous amplitude (envelope) of the signal.

        Args:
            audio: 1D audio array.

        Returns:
            Amplitude envelope array.
        """
        from scipy.signal import hilbert

        # Compute analytic signal and take absolute value for envelope
        analytic_signal = hilbert(audio)
        envelope = np.abs(analytic_signal)

        # Apply light smoothing to reduce noise in envelope
        # Using a simple moving average with ~5ms window
        window_size = max(1, int(len(audio) * 0.005))
        if window_size > 1:
            kernel = np.ones(window_size) / window_size
            envelope = np.convolve(envelope, kernel, mode='same')

        return envelope

    def _measure_duration(self, envelope: np.ndarray) -> int:
        """Measure event duration from onset to offset.

        Args:
            envelope: Normalized amplitude envelope (0-1 range).

        Returns:
            Duration in samples from first onset to last offset.
        """
        # Find onset: first sample above onset threshold
        onset_indices = np.where(envelope >= self.onset_threshold)[0]
        if len(onset_indices) == 0:
            return 0  # No significant event detected

        onset = onset_indices[0]

        # Find offset: last sample above offset threshold
        offset_indices = np.where(envelope >= self.offset_threshold)[0]
        if len(offset_indices) == 0:
            return 0

        offset = offset_indices[-1]

        # Duration is offset - onset
        return max(0, offset - onset)


class SpectralPreFilter:
    """Pre-filter using Harmonic-Percussive Source Separation (HPSS).

    Uses librosa's HPSS algorithm to separate audio into harmonic and
    percussive components. Dog barks have significant harmonic content
    (tonal, horizontal lines in spectrogram) while keyboard clicks are
    purely percussive (transient, vertical lines in spectrogram).

    This filter rejects audio that is predominantly percussive, allowing
    CLAP inference to be skipped for obvious non-bark sounds.
    """

    def __init__(
        self,
        min_harmonic_ratio: float = 0.5,
        margin: float = 3.0,
    ) -> None:
        """Initialize spectral pre-filter.

        Args:
            min_harmonic_ratio: Minimum ratio of harmonic to percussive energy
                                required to pass. Barks typically have ratio > 2.0,
                                keyboard clicks have ratio < 0.3.
            margin: HPSS margin parameter - higher values give better separation
                    but require more computation. Default 3.0 is good balance.
        """
        self.min_harmonic_ratio = min_harmonic_ratio
        self.margin = margin

    def is_harmonic(
        self,
        audio: np.ndarray,
        sample_rate: int,
    ) -> tuple[bool, float]:
        """Check if audio has sufficient harmonic content to be a bark candidate.

        Args:
            audio: Audio array of shape (samples,) or (channels, samples).
                   Should be float32 in range [-1, 1] or int16.
            sample_rate: Sample rate of the audio.

        Returns:
            Tuple of:
            - is_harmonic: True if harmonic ratio exceeds threshold
            - harmonic_ratio: Ratio of harmonic to percussive energy
        """
        import librosa

        # Convert to mono if stereo
        if audio.ndim == 2:
            audio = audio.mean(axis=0)

        # Convert int16 to float32 if needed
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0

        # Ensure float32
        audio = audio.astype(np.float32)

        # Resample to 22050 Hz for librosa (its default and most efficient)
        if sample_rate != 22050:
            audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=22050)

        # Run HPSS to separate harmonic and percussive components
        y_harmonic, y_percussive = librosa.effects.hpss(
            audio,
            margin=self.margin,
        )

        # Calculate energy in each component
        harmonic_energy = np.sum(y_harmonic ** 2)
        percussive_energy = np.sum(y_percussive ** 2)

        # Compute ratio (with small epsilon to avoid division by zero)
        harmonic_ratio = harmonic_energy / (percussive_energy + 1e-10)

        # Check if harmonic content is sufficient
        is_harmonic = harmonic_ratio >= self.min_harmonic_ratio

        return is_harmonic, float(harmonic_ratio)
