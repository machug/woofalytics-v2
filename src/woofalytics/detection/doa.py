"""Direction of Arrival estimation using microphone arrays.

This module implements DOA estimation using the pyargus library,
supporting Bartlett, Capon (MVDR), and Maximum Entropy methods.

Supports both Uniform Linear Array (ULA) and Uniform Circular Array (UCA)
geometries for different microphone hardware configurations.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import structlog
from pyargus.directionEstimation import (
    gen_ula_scanning_vectors,
    gen_uca_scanning_vectors,
    corr_matrix_estimate,
    DOA_Bartlett,
    DOA_Capon,
    DOA_MEM,
)

logger = structlog.get_logger(__name__)


class DirectionEstimator:
    """Estimate direction of arrival using a microphone array.

    Implements three DOA estimation algorithms:
    - Bartlett: Conventional beamforming, simple and robust
    - Capon (MVDR): Minimum variance, higher resolution
    - MEM: Maximum entropy, best for closely-spaced sources

    Supports two array geometries:
    - ULA (Uniform Linear Array): Linear mic arrangement, 0-180° coverage
    - UCA (Uniform Circular Array): Circular mic arrangement, 0-360° coverage
    """

    def __init__(
        self,
        element_spacing: float = 0.1,
        num_elements: int = 2,
        angle_min: int = 0,
        angle_max: int = 180,
        method: str = "bartlett",
        array_type: Literal["ula", "uca"] = "ula",
        radius: float = 0.1,
    ) -> None:
        """Initialize direction estimator.

        Args:
            element_spacing: Inter-element spacing in wavelengths for ULA.
                           For sound at 1kHz, one wavelength is ~34cm.
            num_elements: Number of microphone elements in the array.
            angle_min: Minimum scanning angle in degrees.
            angle_max: Maximum scanning angle in degrees (use 360 for UCA).
            method: DOA algorithm to use: 'bartlett', 'capon', or 'mem'.
            array_type: Array geometry: 'ula' (linear) or 'uca' (circular).
            radius: Array radius in wavelengths for UCA.
                   ReSpeaker 4-Mic Array: ~0.093 at 1kHz (32mm / 343mm).
        """
        self.element_spacing = element_spacing
        self.num_elements = num_elements
        self.angle_min = angle_min
        self.angle_max = angle_max
        self.method = method
        self.array_type = array_type
        self.radius = radius

        # Generate scanning angles
        self._incident_angles = np.arange(angle_min, angle_max + 1, 1)

        # Pre-compute scanning vectors based on array geometry
        if array_type == "uca":
            # Uniform Circular Array - full 360° coverage
            self._scanning_vectors = gen_uca_scanning_vectors(
                num_elements,
                radius,
                np.deg2rad(self._incident_angles),  # UCA expects radians
            )
            logger.debug(
                "doa_estimator_initialized",
                array_type="uca",
                elements=num_elements,
                radius=radius,
                angles=f"{angle_min}-{angle_max}",
            )
        else:
            # Uniform Linear Array - 0-180° coverage
            self._array_alignment = np.arange(0, num_elements, 1) * element_spacing
            self._scanning_vectors = gen_ula_scanning_vectors(
                self._array_alignment,
                self._incident_angles,
            )
            logger.debug(
                "doa_estimator_initialized",
                array_type="ula",
                elements=num_elements,
                spacing=element_spacing,
                angles=f"{angle_min}-{angle_max}",
            )

    def estimate(
        self,
        audio: np.ndarray,
    ) -> tuple[int | None, int | None, int | None]:
        """Estimate direction of arrival for audio.

        Args:
            audio: Audio array of shape (channels, samples).
                  Must have at least 2 channels.

        Returns:
            Tuple of (bartlett_angle, capon_angle, mem_angle) in degrees.
            Only the configured algorithm is run; others are None.
        """
        if audio.shape[0] < 2:
            logger.warning("doa_insufficient_channels", channels=audio.shape[0])
            return (90, None, None) if self.method == "bartlett" else \
                   (None, 90, None) if self.method == "capon" else \
                   (None, None, 90)

        # Transpose to (samples, channels) for correlation estimation
        audio_transposed = audio.T

        try:
            # Estimate correlation matrix
            corr_matrix = corr_matrix_estimate(audio_transposed, imp="fast")

            # Run only the configured DOA algorithm
            if self.method == "capon":
                spectrum = DOA_Capon(corr_matrix, self._scanning_vectors)
                angle = int(self._incident_angles[np.argmax(spectrum)])
                return (None, angle, None)
            elif self.method == "mem":
                spectrum = DOA_MEM(corr_matrix, self._scanning_vectors)
                angle = int(self._incident_angles[np.argmax(spectrum)])
                return (None, None, angle)
            else:  # bartlett (default)
                spectrum = DOA_Bartlett(corr_matrix, self._scanning_vectors)
                angle = int(self._incident_angles[np.argmax(spectrum)])
                return (angle, None, None)

        except Exception as e:
            logger.warning("doa_estimation_error", error=str(e))
            return (90, None, None) if self.method == "bartlett" else \
                   (None, 90, None) if self.method == "capon" else \
                   (None, None, 90)

    def estimate_single(self, audio: np.ndarray) -> int:
        """Estimate DOA using the configured method.

        Args:
            audio: Audio array of shape (channels, samples).

        Returns:
            Estimated angle in degrees.
        """
        bartlett, capon, mem = self.estimate(audio)
        # Return whichever one is not None
        return bartlett if bartlett is not None else \
               capon if capon is not None else \
               mem if mem is not None else 90

    def get_spectrum(
        self,
        audio: np.ndarray,
        method: str = "bartlett",
    ) -> tuple[np.ndarray, np.ndarray]:
        """Get the full DOA spectrum for visualization.

        Args:
            audio: Audio array of shape (channels, samples).
            method: One of "bartlett", "capon", or "mem".

        Returns:
            Tuple of (angles, power_spectrum) for plotting.
        """
        if audio.shape[0] < 2:
            return (self._incident_angles, np.zeros_like(self._incident_angles))

        audio_transposed = audio.T

        try:
            corr_matrix = corr_matrix_estimate(audio_transposed, imp="fast")

            if method == "capon":
                spectrum = DOA_Capon(corr_matrix, self._scanning_vectors)
            elif method == "mem":
                spectrum = DOA_MEM(corr_matrix, self._scanning_vectors)
            else:
                spectrum = DOA_Bartlett(corr_matrix, self._scanning_vectors)

            return (self._incident_angles.copy(), spectrum)

        except Exception as e:
            logger.warning("doa_spectrum_error", error=str(e))
            return (self._incident_angles, np.zeros_like(self._incident_angles))


def angle_to_direction(angle: int, is_circular: bool = False) -> str:
    """Convert angle to human-readable direction.

    Args:
        angle: Angle in degrees.
        is_circular: If True, use 360° compass directions (UCA).
                    If False, use 0-180° left/right directions (ULA).

    Returns:
        Direction string like "front", "left", "back-right", etc.
    """
    if is_circular:
        # UCA: 360° compass-style directions (0° = front)
        # Normalize to 0-360 range
        angle = angle % 360
        if angle < 22.5 or angle >= 337.5:
            return "front"
        elif angle < 67.5:
            return "front-right"
        elif angle < 112.5:
            return "right"
        elif angle < 157.5:
            return "back-right"
        elif angle < 202.5:
            return "back"
        elif angle < 247.5:
            return "back-left"
        elif angle < 292.5:
            return "left"
        else:
            return "front-left"
    else:
        # ULA: 0-180° linear directions
        if angle < 30:
            return "far left"
        elif angle < 60:
            return "left"
        elif angle < 120:
            return "front"
        elif angle < 150:
            return "right"
        else:
            return "far right"
