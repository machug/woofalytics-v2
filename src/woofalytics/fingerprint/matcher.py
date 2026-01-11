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

from woofalytics.fingerprint.acoustic_features import (
    AcousticFeatureExtractor,
    AcousticFeatures,
)
from woofalytics.fingerprint.acoustic_matcher import AcousticMatcher, create_acoustic_matcher
from woofalytics.fingerprint.extractor import FingerprintExtractor
from woofalytics.fingerprint.models import BarkFingerprint, ConfidenceTier, FingerprintMatch
from woofalytics.fingerprint.storage import FingerprintStore


def _get_confidence_tier(confidence: float) -> ConfidenceTier:
    """Classify confidence score into a tier.

    Args:
        confidence: Cosine similarity score (0-1).

    Returns:
        ConfidenceTier based on thresholds.
    """
    # Import here to avoid circular import at module level
    if confidence >= HIGH_CONFIDENCE_THRESHOLD:
        return ConfidenceTier.HIGH
    elif confidence >= MEDIUM_CONFIDENCE_THRESHOLD:
        return ConfidenceTier.MEDIUM
    elif confidence >= LOW_CONFIDENCE_THRESHOLD:
        return ConfidenceTier.LOW
    else:
        return ConfidenceTier.NONE

if TYPE_CHECKING:
    from woofalytics.detection.clap import CLAPDetector

logger = structlog.get_logger(__name__)

# Confidence tier thresholds for auto-tagging decisions
HIGH_CONFIDENCE_THRESHOLD = 0.90  # Auto-tag unconditionally
MEDIUM_CONFIDENCE_THRESHOLD = 0.78  # Auto-tag with margin check
LOW_CONFIDENCE_THRESHOLD = 0.65  # Suggest but don't auto-tag

# Default similarity threshold for matching (lowered from 0.85 to reduce false negatives)
DEFAULT_THRESHOLD = MEDIUM_CONFIDENCE_THRESHOLD

# Minimum margin between best and second-best match required for auto-tagging
# Only applies to medium-confidence matches (high-confidence skips margin check)
MIN_AUTO_TAG_MARGIN = 0.08

# Minimum acoustic score difference to use as tie-breaker
# When CLAP margin is insufficient, use acoustic features if they clearly differ
MIN_ACOUSTIC_TIE_BREAK_MARGIN = 0.12

# Minimum confidence required to update dog profile embedding
# Prevents profile contamination from low-confidence matches
MIN_CONFIDENCE_FOR_EMBEDDING_UPDATE = 0.80


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
        self._acoustic_matcher = create_acoustic_matcher()
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

    def _compute_acoustic_score(
        self,
        bark_features: AcousticFeatures,
        dog_id: str,
    ) -> float:
        """Compute acoustic similarity between bark and dog profile.

        Uses multiple acoustic features weighted by discriminative power:
        - Pitch (20%): Highly discriminative for different dogs
        - Duration (15%): Varies by dog size/temperament
        - Spectral centroid (15%): "Brightness" of bark
        - MFCCs (50%): Timbre fingerprint (most informative)

        Args:
            bark_features: Acoustic features of the current bark.
            dog_id: ID of the dog to compare against.

        Returns:
            Similarity score from 0.0 to 1.0.
        """
        # Get recent fingerprints for this dog to build acoustic reference
        dog_fingerprints = self._store.get_fingerprints_for_dog(dog_id, limit=10)
        if not dog_fingerprints:
            return 0.5  # Neutral score when no reference data

        # Feature weights
        WEIGHT_PITCH = 0.20
        WEIGHT_DURATION = 0.15
        WEIGHT_CENTROID = 0.15
        WEIGHT_MFCC = 0.50

        total_weight = 0.0
        weighted_sum = 0.0

        # Collect reference values from dog's history
        ref_pitches = [fp.pitch_hz for fp in dog_fingerprints if fp.pitch_hz is not None]
        ref_durations = [fp.duration_ms for fp in dog_fingerprints if fp.duration_ms is not None]
        ref_centroids = [fp.spectral_centroid_hz for fp in dog_fingerprints if fp.spectral_centroid_hz is not None]
        ref_mfccs = [fp.mfcc_mean for fp in dog_fingerprints if fp.mfcc_mean is not None]

        # Pitch similarity
        if bark_features.pitch_hz is not None and ref_pitches:
            avg_pitch = np.mean(ref_pitches)
            pitch_range = 1800.0  # 200-2000 Hz typical range
            pitch_diff = abs(bark_features.pitch_hz - avg_pitch) / pitch_range
            pitch_sim = float(np.exp(-pitch_diff * 2.0))
            weighted_sum += pitch_sim * WEIGHT_PITCH
            total_weight += WEIGHT_PITCH

        # Duration similarity
        if bark_features.duration_ms is not None and ref_durations:
            avg_duration = np.mean(ref_durations)
            duration_range = 450.0  # 50-500 ms typical range
            duration_diff = abs(bark_features.duration_ms - avg_duration) / duration_range
            duration_sim = float(np.exp(-duration_diff * 2.0))
            weighted_sum += duration_sim * WEIGHT_DURATION
            total_weight += WEIGHT_DURATION

        # Spectral centroid similarity
        if bark_features.spectral_centroid_hz is not None and ref_centroids:
            avg_centroid = np.mean(ref_centroids)
            centroid_range = 4500.0  # 500-5000 Hz typical range
            centroid_diff = abs(bark_features.spectral_centroid_hz - avg_centroid) / centroid_range
            centroid_sim = float(np.exp(-centroid_diff * 2.0))
            weighted_sum += centroid_sim * WEIGHT_CENTROID
            total_weight += WEIGHT_CENTROID

        # MFCC similarity (cosine similarity)
        if bark_features.mfcc_mean is not None and ref_mfccs:
            # Compute average reference MFCC
            avg_mfcc = np.mean(ref_mfccs, axis=0)

            # Cosine similarity
            norm1 = np.linalg.norm(bark_features.mfcc_mean)
            norm2 = np.linalg.norm(avg_mfcc)

            if norm1 > 1e-10 and norm2 > 1e-10:
                cosine_sim = np.dot(bark_features.mfcc_mean, avg_mfcc) / (norm1 * norm2)
                # Normalize from [-1, 1] to [0, 1]
                mfcc_sim = float((cosine_sim + 1.0) / 2.0)
                weighted_sum += mfcc_sim * WEIGHT_MFCC
                total_weight += WEIGHT_MFCC

        if total_weight < 1e-10:
            return 0.5  # No features to compare

        return weighted_sum / total_weight

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

        # If we have a match, check confidence tier before auto-tagging
        if matches:
            best_match = matches[0]
            confidence_tier = _get_confidence_tier(best_match.confidence)
            best_match.confidence_tier = confidence_tier

            # Assign tiers to all matches
            for match in matches:
                match.confidence_tier = _get_confidence_tier(match.confidence)

            # Determine if we should auto-tag based on confidence tier
            should_tag = False
            margin = None
            acoustic_margin = None

            if confidence_tier == ConfidenceTier.HIGH:
                # High confidence: auto-tag unconditionally (no margin check needed)
                should_tag = True
                logger.info(
                    "high_confidence_auto_tag",
                    fingerprint_id=fingerprint.id,
                    dog_name=best_match.dog_name,
                    confidence=f"{best_match.confidence:.3f}",
                )
            elif confidence_tier == ConfidenceTier.MEDIUM:
                # Medium confidence: require margin check
                if len(matches) == 1:
                    # Only one match - tag it
                    should_tag = True
                else:
                    margin = best_match.confidence - matches[1].confidence
                    if margin >= MIN_AUTO_TAG_MARGIN:
                        # Good margin - tag it
                        should_tag = True
                    else:
                        # Margin insufficient - try acoustic tie-breaking
                        # Uses full acoustic comparison (pitch, duration, centroid, MFCCs)
                        best_acoustic = self._compute_acoustic_score(
                            acoustic_features, best_match.dog_id
                        )
                        second_acoustic = self._compute_acoustic_score(
                            acoustic_features, matches[1].dog_id
                        )
                        acoustic_margin = best_acoustic - second_acoustic

                        # Store acoustic scores on matches for API visibility
                        best_match.acoustic_score = best_acoustic
                        matches[1].acoustic_score = second_acoustic

                        if acoustic_margin >= MIN_ACOUSTIC_TIE_BREAK_MARGIN:
                            # Acoustic features CONFIRM the CLAP winner
                            should_tag = True
                            logger.info(
                                "acoustic_tie_break_confirmed",
                                fingerprint_id=fingerprint.id,
                                winner=best_match.dog_name,
                                best_acoustic=f"{best_acoustic:.3f}",
                                second_acoustic=f"{second_acoustic:.3f}",
                                acoustic_margin=f"{acoustic_margin:.3f}",
                                clap_margin=f"{margin:.3f}",
                            )
                        else:
                            # Acoustics don't confirm - skip auto-tag
                            logger.info(
                                "auto_tag_skipped_insufficient_margin",
                                fingerprint_id=fingerprint.id,
                                best_dog=best_match.dog_name,
                                best_confidence=f"{best_match.confidence:.3f}",
                                confidence_tier=confidence_tier.value,
                                second_dog=matches[1].dog_name,
                                second_confidence=f"{matches[1].confidence:.3f}",
                                clap_margin=f"{margin:.3f}",
                                required_margin=MIN_AUTO_TAG_MARGIN,
                                acoustic_margin=f"{acoustic_margin:.3f}",
                            )
            else:
                # LOW or NONE confidence: don't auto-tag
                logger.info(
                    "auto_tag_skipped_low_confidence",
                    fingerprint_id=fingerprint.id,
                    best_dog=best_match.dog_name,
                    best_confidence=f"{best_match.confidence:.3f}",
                    confidence_tier=confidence_tier.value,
                )

            if should_tag:
                fingerprint.dog_id = best_match.dog_id
                fingerprint.match_confidence = best_match.confidence

                logger.info(
                    "bark_auto_tagged",
                    fingerprint_id=fingerprint.id,
                    dog_id=best_match.dog_id,
                    dog_name=best_match.dog_name,
                    confidence=f"{best_match.confidence:.3f}",
                    confidence_tier=confidence_tier.value,
                    margin=f"{margin:.3f}" if margin else "only_match",
                    detection_prob=f"{detection_prob:.3f}",
                )

                # Update dog profile statistics only if confidence is high enough
                # This prevents profile contamination from borderline matches
                if best_match.confidence >= MIN_CONFIDENCE_FOR_EMBEDDING_UPDATE:
                    self._store.update_dog_stats(
                        dog_id=best_match.dog_id,
                        embedding=embedding,
                        timestamp=timestamp,
                    )
                else:
                    logger.debug(
                        "embedding_update_skipped_low_confidence",
                        dog_id=best_match.dog_id,
                        confidence=f"{best_match.confidence:.3f}",
                        threshold=MIN_CONFIDENCE_FOR_EMBEDDING_UPDATE,
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
