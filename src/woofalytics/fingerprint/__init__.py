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
    DogProfile,
    FingerprintMatch,
)
from woofalytics.fingerprint.storage import FingerprintStore
from woofalytics.fingerprint.extractor import FingerprintExtractor, create_extractor
from woofalytics.fingerprint.matcher import FingerprintMatcher, create_matcher

__all__ = [
    "AcousticFeatureExtractor",
    "AcousticFeatures",
    "AcousticMatcher",
    "BarkFingerprint",
    "DogProfile",
    "FeatureWeights",
    "FingerprintMatch",
    "FingerprintStore",
    "FingerprintExtractor",
    "create_extractor",
    "FingerprintMatcher",
    "create_matcher",
    "create_acoustic_extractor",
    "create_acoustic_matcher",
]
