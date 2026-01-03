"""CLAP embedding extraction for audio fingerprinting.

This module provides the FingerprintExtractor class that extracts 512-dimensional
CLAP embeddings from bark audio samples. It reuses the CLAP model instance from
the detector to avoid loading the model twice.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import structlog

if TYPE_CHECKING:
    from woofalytics.detection.clap import CLAPDetector

logger = structlog.get_logger(__name__)

# CLAP embedding dimension
EMBEDDING_DIM = 512


class FingerprintExtractor:
    """Extracts CLAP embeddings from audio for fingerprinting.

    This class wraps the CLAP detector's embedding extraction capability,
    providing a clean interface for the fingerprint matching pipeline.
    It reuses the existing CLAP model to avoid loading it twice.
    """

    def __init__(self, detector: CLAPDetector) -> None:
        """Initialize the extractor with an existing CLAP detector.

        Args:
            detector: An already-loaded CLAPDetector instance.
                     The detector's model will be used for embedding extraction.
        """
        self._detector = detector
        logger.info(
            "fingerprint_extractor_initialized",
            detector_loaded=detector.is_loaded,
        )

    @property
    def is_ready(self) -> bool:
        """Check if the extractor is ready to process audio."""
        return self._detector.is_loaded

    def ensure_loaded(self) -> None:
        """Ensure the CLAP model is loaded.

        Loads the model if it hasn't been loaded yet.
        """
        if not self._detector.is_loaded:
            logger.info("loading_clap_model_for_extractor")
            self._detector.load()

    def extract_embedding(
        self,
        audio: np.ndarray,
        sample_rate: int = 48000,
    ) -> np.ndarray:
        """Extract a 512-dimensional CLAP embedding from audio.

        The embedding is L2 normalized for cosine similarity comparisons.
        This is the core operation for audio fingerprinting.

        Args:
            audio: Audio array of shape (samples,) or (channels, samples).
                   Should be float32 in range [-1, 1] or int16.
            sample_rate: Sample rate of the audio.

        Returns:
            Normalized 512-dimensional embedding vector (np.float32).

        Raises:
            ValueError: If the audio is empty or invalid.
        """
        self.ensure_loaded()

        # Validate audio
        if audio is None or audio.size == 0:
            raise ValueError("Audio array is empty or None")

        # Extract embedding using the detector's method
        embedding = self._detector.get_audio_embedding(audio, sample_rate)

        # Ensure embedding is normalized (should already be, but verify)
        norm = np.linalg.norm(embedding)
        if norm > 0 and not np.isclose(norm, 1.0, rtol=1e-5):
            embedding = embedding / norm
            logger.debug(
                "embedding_renormalized",
                original_norm=float(norm),
            )

        # Verify dimension
        if embedding.shape != (EMBEDDING_DIM,):
            raise ValueError(
                f"Expected embedding shape ({EMBEDDING_DIM},), "
                f"got {embedding.shape}"
            )

        logger.debug(
            "embedding_extracted",
            shape=embedding.shape,
            norm=float(np.linalg.norm(embedding)),
            dtype=str(embedding.dtype),
        )

        return embedding.astype(np.float32)

    def compute_similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray,
    ) -> float:
        """Compute cosine similarity between two embeddings.

        Both embeddings should be L2 normalized for accurate results.

        Args:
            embedding1: First embedding vector (512-dim).
            embedding2: Second embedding vector (512-dim).

        Returns:
            Cosine similarity score in range [-1, 1].
        """
        # Normalize if needed
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        e1 = embedding1 / norm1 if not np.isclose(norm1, 1.0) else embedding1
        e2 = embedding2 / norm2 if not np.isclose(norm2, 1.0) else embedding2

        return float(np.dot(e1, e2))


def create_extractor(detector: CLAPDetector) -> FingerprintExtractor:
    """Create a fingerprint extractor from an existing CLAP detector.

    This is the recommended way to create an extractor, as it reuses
    the detector's model instance.

    Args:
        detector: An existing CLAPDetector (loaded or not).

    Returns:
        FingerprintExtractor instance.
    """
    return FingerprintExtractor(detector)
