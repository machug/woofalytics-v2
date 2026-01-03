"""Bark detection and direction of arrival modules."""

from woofalytics.detection.model import BarkDetector
from woofalytics.detection.doa import DirectionEstimator
from woofalytics.detection.vad import VADGate, VADConfig

__all__ = ["BarkDetector", "DirectionEstimator", "VADGate", "VADConfig"]
