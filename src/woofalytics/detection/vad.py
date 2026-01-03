"""Voice Activity Detection (VAD) gate for fast rejection.

This module provides a lightweight VAD gate using RMS energy to quickly
skip expensive CLAP inference on silent or near-silent audio frames.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class VADConfig:
    """Configuration for VAD gate."""

    # RMS energy threshold in dB relative to full scale
    # -40 dB is typical for voice activity, -50 dB for very quiet
    energy_threshold_db: float = -40.0

    # Minimum samples required for valid measurement
    min_samples: int = 441  # ~10ms at 44.1kHz


class VADGate:
    """Voice Activity Detection gate using RMS energy.

    This is a fast, lightweight pre-filter to skip expensive CLAP
    inference on silence. Uses RMS (Root Mean Square) energy to
    detect if audio contains meaningful signal.

    Usage:
        vad = VADGate(VADConfig(energy_threshold_db=-45.0))

        if vad.is_active(audio_array):
            # Run expensive CLAP inference
            result = clap_detector.detect(audio_array)
        else:
            # Skip - audio is silent
            pass
    """

    def __init__(self, config: VADConfig | None = None) -> None:
        """Initialize VAD gate.

        Args:
            config: VAD configuration. Uses defaults if None.
        """
        self.config = config or VADConfig()
        self._threshold_linear = self._db_to_linear(self.config.energy_threshold_db)
        self._skipped_count = 0
        self._passed_count = 0

        logger.info(
            "vad_gate_initialized",
            threshold_db=self.config.energy_threshold_db,
            threshold_linear=f"{self._threshold_linear:.6f}",
        )

    @staticmethod
    def _db_to_linear(db: float) -> float:
        """Convert dB to linear amplitude."""
        return 10 ** (db / 20.0)

    @staticmethod
    def _linear_to_db(linear: float) -> float:
        """Convert linear amplitude to dB."""
        if linear <= 0:
            return -float("inf")
        return 20.0 * np.log10(linear)

    def compute_rms_energy(self, audio: np.ndarray) -> float:
        """Compute RMS energy of audio signal.

        Args:
            audio: Audio array of shape (samples,) or (channels, samples).
                   Can be int16 or float32.

        Returns:
            RMS energy as linear amplitude (0.0 to 1.0 for normalized audio).
        """
        # Convert to mono if stereo
        if audio.ndim == 2:
            audio = audio.mean(axis=0)

        # Normalize int16 to float32 [-1, 1]
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        elif audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Compute RMS
        if len(audio) == 0:
            return 0.0

        rms = np.sqrt(np.mean(audio ** 2))
        return float(rms)

    def compute_rms_db(self, audio: np.ndarray) -> float:
        """Compute RMS energy in dB relative to full scale.

        Args:
            audio: Audio array.

        Returns:
            RMS energy in dBFS.
        """
        rms = self.compute_rms_energy(audio)
        return self._linear_to_db(rms)

    def is_active(self, audio: np.ndarray) -> bool:
        """Check if audio contains voice/sound activity.

        Args:
            audio: Audio array of shape (samples,) or (channels, samples).

        Returns:
            True if audio energy exceeds threshold (run inference).
            False if audio is silent (skip inference).
        """
        # Check minimum samples
        num_samples = audio.shape[-1] if audio.ndim > 1 else len(audio)
        if num_samples < self.config.min_samples:
            logger.debug(
                "vad_insufficient_samples",
                samples=num_samples,
                required=self.config.min_samples,
            )
            return False

        rms = self.compute_rms_energy(audio)
        is_active = rms >= self._threshold_linear

        if is_active:
            self._passed_count += 1
        else:
            self._skipped_count += 1

        # Log periodic stats every 100 checks
        total = self._passed_count + self._skipped_count
        if total > 0 and total % 100 == 0:
            skip_rate = self._skipped_count / total * 100
            logger.info(
                "vad_stats",
                passed=self._passed_count,
                skipped=self._skipped_count,
                skip_rate=f"{skip_rate:.1f}%",
                rms_db=f"{self._linear_to_db(rms):.1f}",
            )

        return is_active

    def reset_stats(self) -> None:
        """Reset pass/skip statistics."""
        self._skipped_count = 0
        self._passed_count = 0

    @property
    def stats(self) -> dict:
        """Get VAD statistics."""
        total = self._passed_count + self._skipped_count
        return {
            "passed_count": self._passed_count,
            "skipped_count": self._skipped_count,
            "total_count": total,
            "skip_rate": self._skipped_count / total if total > 0 else 0.0,
        }
