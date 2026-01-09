"""Bark detection and direction of arrival modules."""

from woofalytics.detection.doa import DirectionEstimator
from woofalytics.detection.model import BarkDetector
from woofalytics.detection.resample_cache import AudioResampleCache
from woofalytics.detection.vad import VADConfig, VADGate
from woofalytics.detection.yamnet import YAMNetConfig, YAMNetGate

__all__ = [
    "AudioResampleCache",
    "BarkDetector",
    "DirectionEstimator",
    "VADConfig",
    "VADGate",
    "YAMNetConfig",
    "YAMNetGate",
]
