"""Evidence collection system.

This module provides evidence recording with structured metadata
for council complaints and legal documentation.
"""

from woofalytics.evidence.metadata import (
    DetectionInfo,
    DeviceInfo,
    EvidenceMetadata,
    EvidenceIndex,
)
from woofalytics.evidence.storage import EvidenceStorage, PendingRecording

__all__ = [
    "DetectionInfo",
    "DeviceInfo",
    "EvidenceMetadata",
    "EvidenceIndex",
    "EvidenceStorage",
    "PendingRecording",
]
