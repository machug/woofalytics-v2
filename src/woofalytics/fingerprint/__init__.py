"""Audio fingerprinting for dog identification.

This module provides fingerprint-based recognition of individual dogs
by their bark characteristics using CLAP embeddings and acoustic features.
"""

from woofalytics.fingerprint.acoustic_features import (
    AcousticFeatureExtractor,
    AcousticFeatures,
    create_acoustic_extractor,
)
from woofalytics.fingerprint.acoustic_matcher import (
    AcousticMatcher,
    FeatureWeights,
    create_acoustic_matcher,
)
from woofalytics.fingerprint.clustering import (
    BarkClusterer,
    ClusterSuggestion,
    create_clusterer,
    is_clustering_available,
)
from woofalytics.fingerprint.extractor import FingerprintExtractor, create_extractor
from woofalytics.fingerprint.matcher import FingerprintMatcher, create_matcher
from woofalytics.fingerprint.models import (
    BarkFingerprint,
    ConfidenceTier,
    DogProfile,
    FingerprintMatch,
)
from woofalytics.fingerprint.storage import FingerprintStore

__all__ = [
    "AcousticFeatureExtractor",
    "AcousticFeatures",
    "AcousticMatcher",
    "BarkClusterer",
    "BarkFingerprint",
    "ClusterSuggestion",
    "ConfidenceTier",
    "DogProfile",
    "FeatureWeights",
    "FingerprintMatch",
    "FingerprintStore",
    "FingerprintExtractor",
    "FingerprintMatcher",
    "create_acoustic_extractor",
    "create_acoustic_matcher",
    "create_clusterer",
    "create_extractor",
    "create_matcher",
    "is_clustering_available",
]
