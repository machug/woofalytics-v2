"""Acoustic feature extraction for secondary fingerprinting.

This module extracts interpretable acoustic characteristics from bark audio
segments to supplement CLAP embeddings for dog identification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import structlog

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = structlog.get_logger(__name__)

# Try to import scipy for signal processing
try:
    from scipy.fft import rfft, rfftfreq

    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    logger.warning("scipy not available, some features may be limited")

# Try to import librosa for advanced pitch detection
try:
    import librosa

    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False
    logger.debug("librosa not available, using autocorrelation for pitch detection")


@dataclass
class AcousticFeatures:
    """Acoustic features extracted from a bark audio segment.

    These features provide interpretable characteristics that complement
    the CLAP embedding for fingerprint matching and dog identification.
    """

    duration_ms: float
    """Duration of the audio segment in milliseconds."""

    pitch_hz: float | None
    """Fundamental frequency (F0) in Hz, or None if undetectable."""

    spectral_centroid_hz: float
    """Spectral centroid - "brightness" of the sound in Hz."""

    spectral_rolloff_hz: float
    """Frequency below which 85% of spectral energy is contained."""

    spectral_bandwidth_hz: float
    """Spread of the spectrum around the centroid."""

    zero_crossing_rate: float
    """Rate of sign changes in the signal (related to noisiness)."""

    mfcc_mean: NDArray[np.floating]
    """Mean of 13 MFCCs across frames, shape (13,)."""

    mfcc_std: NDArray[np.floating]
    """Standard deviation of 13 MFCCs across frames, shape (13,)."""

    energy_db: float
    """RMS energy in decibels."""

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "duration_ms": self.duration_ms,
            "pitch_hz": self.pitch_hz,
            "spectral_centroid_hz": self.spectral_centroid_hz,
            "spectral_rolloff_hz": self.spectral_rolloff_hz,
            "spectral_bandwidth_hz": self.spectral_bandwidth_hz,
            "zero_crossing_rate": self.zero_crossing_rate,
            "mfcc_mean": self.mfcc_mean.tolist(),
            "mfcc_std": self.mfcc_std.tolist(),
            "energy_db": self.energy_db,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AcousticFeatures:
        """Create from dictionary."""
        return cls(
            duration_ms=data["duration_ms"],
            pitch_hz=data.get("pitch_hz"),
            spectral_centroid_hz=data["spectral_centroid_hz"],
            spectral_rolloff_hz=data["spectral_rolloff_hz"],
            spectral_bandwidth_hz=data["spectral_bandwidth_hz"],
            zero_crossing_rate=data["zero_crossing_rate"],
            mfcc_mean=np.array(data["mfcc_mean"]),
            mfcc_std=np.array(data["mfcc_std"]),
            energy_db=data["energy_db"],
        )


class AcousticFeatureExtractor:
    """Extract acoustic features from audio segments.

    Uses scipy for signal processing and optionally librosa for
    advanced pitch detection via pYIN.
    """

    # Typical dog bark frequency range
    MIN_PITCH_HZ = 100.0
    MAX_PITCH_HZ = 2000.0

    # MFCC parameters
    N_MFCCS = 13
    N_MELS = 40
    FFT_SIZE = 2048
    HOP_LENGTH = 512

    def __init__(self, sample_rate: int = 48000) -> None:
        """Initialize the feature extractor.

        Args:
            sample_rate: Expected sample rate of input audio.
        """
        self.sample_rate = sample_rate
        self._log = logger.bind(sample_rate=sample_rate)

        # Pre-compute mel filterbank if scipy available
        self._mel_filterbank: NDArray[np.floating] | None = None
        if HAS_SCIPY:
            self._mel_filterbank = self._create_mel_filterbank()

    def _create_mel_filterbank(self) -> NDArray[np.floating]:
        """Create a mel filterbank matrix for MFCC computation."""
        n_fft_bins = self.FFT_SIZE // 2 + 1

        # Mel scale conversion functions
        def hz_to_mel(hz: float) -> float:
            return 2595.0 * np.log10(1.0 + hz / 700.0)

        def mel_to_hz(mel: float) -> float:
            return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

        # Create mel-spaced filter points
        low_mel = hz_to_mel(0)
        high_mel = hz_to_mel(self.sample_rate / 2)
        mel_points = np.linspace(low_mel, high_mel, self.N_MELS + 2)
        hz_points = np.array([mel_to_hz(m) for m in mel_points])

        # Convert to FFT bin indices
        bin_indices = np.floor((self.FFT_SIZE + 1) * hz_points / self.sample_rate).astype(int)

        # Create filterbank
        filterbank = np.zeros((self.N_MELS, n_fft_bins))
        for i in range(self.N_MELS):
            left = bin_indices[i]
            center = bin_indices[i + 1]
            right = bin_indices[i + 2]

            # Rising edge
            for j in range(left, center):
                if center > left:
                    filterbank[i, j] = (j - left) / (center - left)

            # Falling edge
            for j in range(center, right):
                if right > center:
                    filterbank[i, j] = (right - j) / (right - center)

        return filterbank

    def extract(self, audio: NDArray[np.floating]) -> AcousticFeatures:
        """Extract all acoustic features from an audio segment.

        Args:
            audio: Audio samples as float array, shape (samples,) or (channels, samples).
                   Expected range [-1, 1] or will be normalized.

        Returns:
            AcousticFeatures containing all extracted characteristics.

        Raises:
            ValueError: If audio is too short for analysis.
        """
        # Ensure 1D mono audio
        if audio.ndim == 2:
            audio = audio.mean(axis=0)
        audio = audio.astype(np.float64)

        # Normalize if needed
        max_val = np.abs(audio).max()
        if max_val > 1.0:
            audio = audio / max_val
        elif max_val < 1e-10:
            # Silence - return default features
            self._log.debug("audio_is_silence", max_amplitude=max_val)
            return self._silence_features(len(audio))

        # Calculate duration
        duration_ms = len(audio) / self.sample_rate * 1000.0

        # Minimum length check
        min_samples = self.FFT_SIZE
        if len(audio) < min_samples:
            self._log.warning(
                "audio_too_short",
                samples=len(audio),
                min_required=min_samples,
                duration_ms=duration_ms,
            )
            # Pad with zeros if too short
            audio = np.pad(audio, (0, min_samples - len(audio)))

        # Extract individual features
        pitch_hz = self.extract_pitch(audio)
        spectral = self.extract_spectral(audio)
        zcr = self._compute_zero_crossing_rate(audio)
        mfcc_mean, mfcc_std = self.extract_mfccs(audio)
        energy_db = self._compute_energy_db(audio)

        features = AcousticFeatures(
            duration_ms=duration_ms,
            pitch_hz=pitch_hz,
            spectral_centroid_hz=spectral["centroid"],
            spectral_rolloff_hz=spectral["rolloff"],
            spectral_bandwidth_hz=spectral["bandwidth"],
            zero_crossing_rate=zcr,
            mfcc_mean=mfcc_mean,
            mfcc_std=mfcc_std,
            energy_db=energy_db,
        )

        self._log.debug(
            "features_extracted",
            duration_ms=round(duration_ms, 1),
            pitch_hz=round(pitch_hz, 1) if pitch_hz else None,
            centroid_hz=round(spectral["centroid"], 1),
            energy_db=round(energy_db, 1),
        )

        return features

    def extract_pitch(self, audio: NDArray[np.floating]) -> float | None:
        """Extract fundamental frequency (F0) using pitch detection.

        Uses librosa's pYIN if available, otherwise falls back to
        autocorrelation-based pitch detection.

        Args:
            audio: Mono audio samples.

        Returns:
            Estimated fundamental frequency in Hz, or None if undetectable.
        """
        if HAS_LIBROSA:
            return self._extract_pitch_pyin(audio)
        else:
            return self._extract_pitch_autocorr(audio)

    def _extract_pitch_pyin(self, audio: NDArray[np.floating]) -> float | None:
        """Extract pitch using librosa's pYIN algorithm."""
        try:
            f0, voiced_flag, _ = librosa.pyin(
                audio.astype(np.float32),
                fmin=self.MIN_PITCH_HZ,
                fmax=self.MAX_PITCH_HZ,
                sr=self.sample_rate,
                frame_length=self.FFT_SIZE,
                hop_length=self.HOP_LENGTH,
            )

            # Get median of voiced frames
            voiced_f0 = f0[voiced_flag]
            if len(voiced_f0) > 0:
                pitch = float(np.median(voiced_f0))
                if np.isfinite(pitch):
                    return pitch

        except Exception as e:
            self._log.warning("pyin_pitch_failed", error=str(e))

        return None

    def _extract_pitch_autocorr(self, audio: NDArray[np.floating]) -> float | None:
        """Extract pitch using autocorrelation method.

        This is a fallback when librosa is not available.
        """
        # Calculate lag range for expected pitch frequencies
        min_lag = int(self.sample_rate / self.MAX_PITCH_HZ)
        max_lag = int(self.sample_rate / self.MIN_PITCH_HZ)

        # Limit max_lag to audio length
        max_lag = min(max_lag, len(audio) // 2)

        if max_lag <= min_lag:
            return None

        # Compute autocorrelation using numpy
        # Normalize audio first
        audio_norm = audio - np.mean(audio)
        if np.std(audio_norm) < 1e-10:
            return None

        # Use numpy correlate for autocorrelation
        autocorr = np.correlate(audio_norm, audio_norm, mode="full")
        autocorr = autocorr[len(autocorr) // 2 :]  # Take positive lags

        # Find peaks in the expected range
        search_range = autocorr[min_lag:max_lag]
        if len(search_range) == 0:
            return None

        # Find the first significant peak
        peak_idx = np.argmax(search_range)
        peak_lag = peak_idx + min_lag

        # Verify it's actually a peak (not just the global max)
        if peak_lag > 0 and autocorr[peak_lag] > 0.2 * autocorr[0]:
            pitch = self.sample_rate / peak_lag
            if self.MIN_PITCH_HZ <= pitch <= self.MAX_PITCH_HZ:
                return float(pitch)

        return None

    def extract_mfccs(
        self, audio: NDArray[np.floating]
    ) -> tuple[NDArray[np.floating], NDArray[np.floating]]:
        """Extract MFCC features from audio.

        Args:
            audio: Mono audio samples.

        Returns:
            Tuple of (mean MFCCs, std MFCCs), each of shape (13,).
        """
        if HAS_LIBROSA:
            return self._extract_mfccs_librosa(audio)
        elif HAS_SCIPY and self._mel_filterbank is not None:
            return self._extract_mfccs_scipy(audio)
        else:
            # Return zeros if no library available
            return np.zeros(self.N_MFCCS), np.zeros(self.N_MFCCS)

    def _extract_mfccs_librosa(
        self, audio: NDArray[np.floating]
    ) -> tuple[NDArray[np.floating], NDArray[np.floating]]:
        """Extract MFCCs using librosa."""
        try:
            mfccs = librosa.feature.mfcc(
                y=audio.astype(np.float32),
                sr=self.sample_rate,
                n_mfcc=self.N_MFCCS,
                n_fft=self.FFT_SIZE,
                hop_length=self.HOP_LENGTH,
                n_mels=self.N_MELS,
            )
            return np.mean(mfccs, axis=1), np.std(mfccs, axis=1)
        except Exception as e:
            self._log.warning("librosa_mfcc_failed", error=str(e))
            return np.zeros(self.N_MFCCS), np.zeros(self.N_MFCCS)

    def _extract_mfccs_scipy(
        self, audio: NDArray[np.floating]
    ) -> tuple[NDArray[np.floating], NDArray[np.floating]]:
        """Extract MFCCs using scipy (manual implementation)."""
        # Frame the signal
        n_frames = 1 + (len(audio) - self.FFT_SIZE) // self.HOP_LENGTH
        if n_frames < 1:
            return np.zeros(self.N_MFCCS), np.zeros(self.N_MFCCS)

        # Create frames
        frames = np.zeros((n_frames, self.FFT_SIZE))
        for i in range(n_frames):
            start = i * self.HOP_LENGTH
            frames[i] = audio[start : start + self.FFT_SIZE]

        # Apply Hamming window
        window = np.hamming(self.FFT_SIZE)
        frames = frames * window

        # Compute power spectrum
        power_spectrum = np.abs(rfft(frames, axis=1)) ** 2
        power_spectrum = np.maximum(power_spectrum, 1e-10)  # Avoid log(0)

        # Apply mel filterbank
        mel_spectrum = np.dot(power_spectrum, self._mel_filterbank.T)
        mel_spectrum = np.maximum(mel_spectrum, 1e-10)

        # Log mel spectrum
        log_mel = np.log(mel_spectrum)

        # DCT to get MFCCs
        # Type-II DCT (ortho normalized)
        n = self.N_MELS
        dct_matrix = np.zeros((self.N_MFCCS, n))
        for i in range(self.N_MFCCS):
            for j in range(n):
                dct_matrix[i, j] = np.cos(np.pi * i * (2 * j + 1) / (2 * n))
        dct_matrix *= np.sqrt(2.0 / n)
        dct_matrix[0] *= np.sqrt(0.5)

        mfccs = np.dot(log_mel, dct_matrix.T)

        return np.mean(mfccs, axis=0), np.std(mfccs, axis=0)

    def extract_spectral(self, audio: NDArray[np.floating]) -> dict[str, float]:
        """Extract spectral features: centroid, rolloff, and bandwidth.

        Args:
            audio: Mono audio samples.

        Returns:
            Dictionary with 'centroid', 'rolloff', and 'bandwidth' in Hz.
        """
        if HAS_LIBROSA:
            return self._extract_spectral_librosa(audio)
        elif HAS_SCIPY:
            return self._extract_spectral_scipy(audio)
        else:
            return {"centroid": 0.0, "rolloff": 0.0, "bandwidth": 0.0}

    def _extract_spectral_librosa(self, audio: NDArray[np.floating]) -> dict[str, float]:
        """Extract spectral features using librosa."""
        try:
            audio_f32 = audio.astype(np.float32)

            # Compute STFT
            S = np.abs(librosa.stft(audio_f32, n_fft=self.FFT_SIZE, hop_length=self.HOP_LENGTH))

            # Spectral centroid
            centroid = librosa.feature.spectral_centroid(
                S=S, sr=self.sample_rate, n_fft=self.FFT_SIZE, hop_length=self.HOP_LENGTH
            )

            # Spectral rolloff (85% energy)
            rolloff = librosa.feature.spectral_rolloff(
                S=S, sr=self.sample_rate, roll_percent=0.85
            )

            # Spectral bandwidth
            bandwidth = librosa.feature.spectral_bandwidth(
                S=S, sr=self.sample_rate, n_fft=self.FFT_SIZE, hop_length=self.HOP_LENGTH
            )

            return {
                "centroid": float(np.mean(centroid)),
                "rolloff": float(np.mean(rolloff)),
                "bandwidth": float(np.mean(bandwidth)),
            }
        except Exception as e:
            self._log.warning("librosa_spectral_failed", error=str(e))
            return {"centroid": 0.0, "rolloff": 0.0, "bandwidth": 0.0}

    def _extract_spectral_scipy(self, audio: NDArray[np.floating]) -> dict[str, float]:
        """Extract spectral features using scipy."""
        # Compute power spectrum
        freqs = rfftfreq(self.FFT_SIZE, 1.0 / self.sample_rate)
        spectrum = np.abs(rfft(audio, n=self.FFT_SIZE)) ** 2

        # Avoid division by zero
        total_power = np.sum(spectrum)
        if total_power < 1e-10:
            return {"centroid": 0.0, "rolloff": 0.0, "bandwidth": 0.0}

        # Spectral centroid: weighted mean of frequencies
        centroid = np.sum(freqs * spectrum) / total_power

        # Spectral rolloff: frequency below which 85% of energy
        cumsum = np.cumsum(spectrum)
        rolloff_idx = np.searchsorted(cumsum, 0.85 * total_power)
        rolloff = freqs[min(rolloff_idx, len(freqs) - 1)]

        # Spectral bandwidth: weighted std of frequencies around centroid
        bandwidth = np.sqrt(np.sum(((freqs - centroid) ** 2) * spectrum) / total_power)

        return {
            "centroid": float(centroid),
            "rolloff": float(rolloff),
            "bandwidth": float(bandwidth),
        }

    def _compute_zero_crossing_rate(self, audio: NDArray[np.floating]) -> float:
        """Compute the zero-crossing rate of the audio.

        Args:
            audio: Mono audio samples.

        Returns:
            Zero-crossing rate (crossings per sample).
        """
        if len(audio) < 2:
            return 0.0

        # Count sign changes
        signs = np.sign(audio)
        crossings = np.sum(np.abs(np.diff(signs)) > 0)

        return float(crossings / (len(audio) - 1))

    def _compute_energy_db(self, audio: NDArray[np.floating]) -> float:
        """Compute RMS energy in decibels.

        Args:
            audio: Mono audio samples.

        Returns:
            RMS energy in dB (relative to full scale).
        """
        rms = np.sqrt(np.mean(audio**2))
        if rms < 1e-10:
            return -100.0  # Effectively silence

        # Convert to dB (0 dB = full scale)
        return float(20.0 * np.log10(rms))

    def _silence_features(self, n_samples: int) -> AcousticFeatures:
        """Return features for silent audio."""
        duration_ms = n_samples / self.sample_rate * 1000.0
        return AcousticFeatures(
            duration_ms=duration_ms,
            pitch_hz=None,
            spectral_centroid_hz=0.0,
            spectral_rolloff_hz=0.0,
            spectral_bandwidth_hz=0.0,
            zero_crossing_rate=0.0,
            mfcc_mean=np.zeros(self.N_MFCCS),
            mfcc_std=np.zeros(self.N_MFCCS),
            energy_db=-100.0,
        )


def create_acoustic_extractor(sample_rate: int = 48000) -> AcousticFeatureExtractor:
    """Create an acoustic feature extractor with default settings.

    Args:
        sample_rate: Expected sample rate of input audio.

    Returns:
        Configured AcousticFeatureExtractor instance.
    """
    return AcousticFeatureExtractor(sample_rate=sample_rate)
