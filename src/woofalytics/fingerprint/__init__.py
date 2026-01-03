"""Audio fingerprinting for dog identification.

This module provides fingerprint-based recognition of individual dogs
by their bark characteristics using CLAP embeddings.
"""

from woofalytics.fingerprint.models import (
    DogProfile,
    BarkFingerprint,
    FingerprintMatch,
    ClusterInfo,
)
from woofalytics.fingerprint.storage import FingerprintStore
from woofalytics.fingerprint.extractor import FingerprintExtractor, create_extractor
from woofalytics.fingerprint.matcher import FingerprintMatcher, create_matcher

__all__ = [
    "DogProfile",
    "BarkFingerprint",
    "FingerprintMatch",
    "ClusterInfo",
    "FingerprintStore",
    "FingerprintExtractor",
    "create_extractor",
    "FingerprintMatcher",
    "create_matcher",
]
