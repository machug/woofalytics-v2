"""Fingerprint matching engine for dog identification.

This module provides the FingerprintMatcher class that combines embedding
extraction and storage to identify dogs from their bark audio. It implements
the full matching pipeline from raw audio to identified dog profiles.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import numpy as np
import structlog

from woofalytics.fingerprint.acoustic_features import AcousticFeatureExtractor
from woofalytics.fingerprint.extractor import FingerprintExtractor
from woofalytics.fingerprint.models import BarkFingerprint, FingerprintMatch
from woofalytics.fingerprint.storage import FingerprintStore

if TYPE_CHECKING:
    from woofalytics.detection.clap import CLAPDetector

logger = structlog.get_logger(__name__)

# Default similarity threshold for matching
DEFAULT_THRESHOLD = 0.75


class FingerprintMatcher:
    """Matching engine that identifies dogs from bark audio.

    This class combines the fingerprint extractor and storage to provide
    a complete matching pipeline. It can:
    - Match audio against known dog profiles
    - Process new barks and save fingerprints
    - Update dog profile statistics when matches are found
    """

    def __init__(
        self,
        detector: CLAPDetector,
        store: FingerprintStore,
        threshold: float = DEFAULT_THRESHOLD,
        sample_rate: int = 48000,
    ) -> None:
        """Initialize the matcher with detector and storage.

        Args:
            detector: CLAP detector for embedding extraction.
            store: Fingerprint storage for profiles and matching.
            threshold: Minimum similarity to consider a match (0-1).
            sample_rate: Audio sample rate for acoustic feature extraction.
        """
        self._extractor = FingerprintExtractor(detector)
        self._acoustic_extractor = AcousticFeatureExtractor(sample_rate=sample_rate)
        self._store = store
        self._threshold = threshold
        self._sample_rate = sample_rate

        logger.info(
            "fingerprint_matcher_initialized",
            threshold=threshold,
            sample_rate=sample_rate,
            extractor_ready=self._extractor.is_ready,
        )

    @property
    def threshold(self) -> float:
        """Get the current match threshold."""
        return self._threshold

    @threshold.setter
    def threshold(self, value: float) -> None:
        """Set the match threshold.

        Args:
            value: New threshold value (0-1).
        """
        if not 0.0 <= value <= 1.0:
            raise ValueError("Threshold must be between 0 and 1")
        self._threshold = value
        logger.debug("threshold_updated", threshold=value)

    def match(
        self,
        audio: np.ndarray,
        sample_rate: int = 48000,
        threshold: float | None = None,
        top_k: int = 3,
        only_auto_taggable: bool = False,
    ) -> list[FingerprintMatch]:
        """Match audio against known dog profiles.

        Extracts the embedding from the audio and searches for matching
        dog profiles in the storage.

        Args:
            audio: Audio array of shape (samples,) or (channels, samples).
            sample_rate: Sample rate of the audio.
            threshold: Override the default threshold for this match.
            top_k: Maximum number of matches to return.
            only_auto_taggable: If True, only match against confirmed dogs
                with sufficient samples. Default False for manual matching.

        Returns:
            List of matches sorted by confidence (highest first).
            Empty list if no matches found above threshold.
        """
        threshold = threshold if threshold is not None else self._threshold

        # Extract embedding from audio
        embedding = self._extractor.extract_embedding(audio, sample_rate)

        # Find matches in storage (include all dogs for manual matching)
        matches = self._store.find_matches(
            embedding=embedding,
            threshold=threshold,
            top_k=top_k,
            only_auto_taggable=only_auto_taggable,
        )

        if matches:
            logger.info(
                "matches_found",
                count=len(matches),
                best_match=matches[0].dog_name,
                best_confidence=f"{matches[0].confidence:.3f}",
            )
        else:
            logger.debug(
                "no_matches_found",
                threshold=threshold,
            )

        return matches

    def process_bark(
        self,
        audio: np.ndarray,
        sample_rate: int = 48000,
        detection_prob: float = 0.0,
        doa: int | None = None,
        evidence_filename: str | None = None,
    ) -> tuple[BarkFingerprint, list[FingerprintMatch]]:
        """Process a detected bark: extract, save, match, and update stats.

        This is the main entry point for processing a new bark detection.
        It performs the complete pipeline:
        1. Extract CLAP embedding from audio
        2. Find matches against known dog profiles
        3. Create and save a BarkFingerprint record
        4. If a match is found, update the dog's profile statistics

        Args:
            audio: Audio array containing the bark.
            sample_rate: Sample rate of the audio.
            detection_prob: Probability from the bark detector (0-1).
            doa: Direction of arrival in degrees (if available).
            evidence_filename: Path to saved audio file (if recorded).

        Returns:
            Tuple of:
            - BarkFingerprint: The saved fingerprint record
            - list[FingerprintMatch]: Matches found (may be empty)
        """
        timestamp = datetime.now(timezone.utc)

        # Extract CLAP embedding
        embedding = self._extractor.extract_embedding(audio, sample_rate)

        # Extract acoustic features for secondary fingerprinting
        acoustic_features = self._acoustic_extractor.extract(audio)

        # Find matches against confirmed dogs only (auto-tagging)
        # Dogs must be confirmed AND have sufficient samples to be matched
        matches = self._store.find_matches(
            embedding=embedding,
            threshold=self._threshold,
            top_k=3,
            only_auto_taggable=True,  # Only match confirmed dogs with enough samples
        )

        # Create fingerprint record with acoustic features
        fingerprint = BarkFingerprint(
            timestamp=timestamp,
            embedding=embedding,
            detection_probability=detection_prob,
            doa_degrees=doa,
            evidence_filename=evidence_filename,
            duration_ms=acoustic_features.duration_ms,
            pitch_hz=acoustic_features.pitch_hz,
            spectral_centroid_hz=acoustic_features.spectral_centroid_hz,
            mfcc_mean=acoustic_features.mfcc_mean,
        )

        # If we have a match, link to the dog
        if matches:
            best_match = matches[0]
            fingerprint.dog_id = best_match.dog_id
            fingerprint.match_confidence = best_match.confidence

            logger.info(
                "bark_auto_tagged",
                fingerprint_id=fingerprint.id,
                dog_id=best_match.dog_id,
                dog_name=best_match.dog_name,
                confidence=f"{best_match.confidence:.3f}",
                detection_prob=f"{detection_prob:.3f}",
            )

            # Update dog profile statistics
            self._store.update_dog_stats(
                dog_id=best_match.dog_id,
                embedding=embedding,
                timestamp=timestamp,
            )
        else:
            # No auto-taggable match found - bark will be untagged
            # Check if there are any potential matches (for logging)
            potential_matches = self._store.find_matches(
                embedding=embedding,
                threshold=self._threshold,
                top_k=1,
                only_auto_taggable=False,
            )
            if potential_matches:
                logger.info(
                    "bark_awaiting_confirmation",
                    fingerprint_id=fingerprint.id,
                    potential_dog=potential_matches[0].dog_name,
                    potential_confidence=f"{potential_matches[0].confidence:.3f}",
                    detection_prob=f"{detection_prob:.3f}",
                    reason="Dog not confirmed or insufficient samples",
                )
            else:
                logger.info(
                    "bark_unmatched",
                    fingerprint_id=fingerprint.id,
                    detection_prob=f"{detection_prob:.3f}",
                )

        # Save fingerprint
        self._store.save_fingerprint(fingerprint)

        return fingerprint, matches

    def get_embedding(
        self,
        audio: np.ndarray,
        sample_rate: int = 48000,
    ) -> np.ndarray:
        """Extract embedding without matching or saving.

        Useful for testing or when you need just the embedding.

        Args:
            audio: Audio array containing the bark.
            sample_rate: Sample rate of the audio.

        Returns:
            Normalized 512-dimensional embedding vector.
        """
        return self._extractor.extract_embedding(audio, sample_rate)

    def get_stats(self) -> dict[str, int | float]:
        """Get statistics about the fingerprint database.

        Returns:
            Dictionary with counts and settings.
        """
        store_stats = self._store.get_stats()
        return {
            **store_stats,
            "threshold": self._threshold,
        }


def create_matcher(
    detector: CLAPDetector,
    store: FingerprintStore,
    threshold: float = DEFAULT_THRESHOLD,
    sample_rate: int = 48000,
) -> FingerprintMatcher:
    """Create a fingerprint matcher from detector and storage.

    This is the recommended way to create a matcher.

    Args:
        detector: CLAP detector (loaded or not).
        store: Fingerprint storage instance.
        threshold: Match similarity threshold.
        sample_rate: Audio sample rate for acoustic feature extraction.

    Returns:
        FingerprintMatcher instance.
    """
    return FingerprintMatcher(detector, store, threshold, sample_rate)
