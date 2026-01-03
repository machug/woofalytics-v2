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
from woofalytics.fingerprint.models import (
    BarkFingerprint,
    ClusterInfo,
    DogProfile,
    FingerprintMatch,
)
from woofalytics.fingerprint.storage import FingerprintStore

__all__ = [
    "AcousticFeatureExtractor",
    "AcousticFeatures",
    "AcousticMatcher",
    "BarkFingerprint",
    "ClusterInfo",
    "DogProfile",
    "FeatureWeights",
    "FingerprintMatch",
    "FingerprintStore",
    "create_acoustic_extractor",
    "create_acoustic_matcher",
]
