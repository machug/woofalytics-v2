"""Tests for audio modules."""

from __future__ import annotations

import time

import numpy as np
import pytest

from woofalytics.audio.capture import AudioFrame
from woofalytics.audio.devices import MicrophoneInfo


class TestMicrophoneInfo:
    """Tests for MicrophoneInfo dataclass."""

    def test_creation(self):
        """Test microphone info creation."""
        mic = MicrophoneInfo(
            index=0,
            name="Test Microphone",
            channels=2,
            sample_rate=44100,
            is_default=True,
        )

        assert mic.index == 0
        assert mic.name == "Test Microphone"
        assert mic.channels == 2
        assert mic.sample_rate == 44100
        assert mic.is_default is True

    def test_str(self):
        """Test string representation."""
        mic = MicrophoneInfo(
            index=0,
            name="Test Mic",
            channels=2,
            sample_rate=44100,
            is_default=True,
        )

        s = str(mic)

        assert "[0]" in s
        assert "Test Mic" in s
        assert "2ch" in s
        assert "44100Hz" in s
        assert "(default)" in s

    def test_str_no_default(self):
        """Test string without default marker."""
        mic = MicrophoneInfo(
            index=1,
            name="Other Mic",
            channels=4,
            sample_rate=48000,
            is_default=False,
        )

        s = str(mic)

        assert "(default)" not in s


class TestAudioFrame:
    """Tests for AudioFrame dataclass."""

    def test_creation(self):
        """Test audio frame creation."""
        data = b"\x00" * 1764  # 441 samples * 2 channels * 2 bytes

        frame = AudioFrame(
            timestamp=time.time(),
            data=data,
            channels=2,
            sample_rate=44100,
        )

        assert frame.channels == 2
        assert frame.sample_rate == 44100
        assert len(frame.data) == 1764

    def test_to_numpy(self):
        """Test numpy conversion."""
        # Create known data
        samples = 100
        channels = 2
        audio = np.arange(samples * channels, dtype=np.int16)

        frame = AudioFrame(
            timestamp=time.time(),
            data=audio.tobytes(),
            channels=channels,
            sample_rate=44100,
        )

        arr = frame.to_numpy()

        assert arr.shape == (channels, samples)
        assert arr.dtype == np.int16

    def test_duration_ms(self):
        """Test duration calculation."""
        # 441 samples at 44100 Hz = 10ms
        samples = 441
        channels = 2
        data = b"\x00" * (samples * channels * 2)

        frame = AudioFrame(
            timestamp=time.time(),
            data=data,
            channels=channels,
            sample_rate=44100,
        )

        assert frame.duration_ms == pytest.approx(10.0, rel=0.01)

    def test_duration_different_rate(self):
        """Test duration with different sample rate."""
        # 480 samples at 48000 Hz = 10ms
        samples = 480
        channels = 2
        data = b"\x00" * (samples * channels * 2)

        frame = AudioFrame(
            timestamp=time.time(),
            data=data,
            channels=channels,
            sample_rate=48000,
        )

        assert frame.duration_ms == pytest.approx(10.0, rel=0.01)


class TestListMicrophones:
    """Tests for list_microphones function."""

    def test_with_mock(self, mock_pyaudio):
        """Test microphone listing with mocked PyAudio."""
        from woofalytics.audio.devices import list_microphones

        devices = list_microphones(min_channels=2)

        assert len(devices) == 2
        assert devices[0].name == "Test Microphone"
        assert devices[1].name == "ReSpeaker 2-Mic HAT"


class TestFindMicrophone:
    """Tests for find_microphone function."""

    def test_auto_detect(self, mock_pyaudio):
        """Test auto-detection of microphone."""
        from woofalytics.audio.devices import find_microphone

        mic = find_microphone()

        assert mic is not None
        assert mic.channels >= 2

    def test_by_name(self, mock_pyaudio):
        """Test finding microphone by name."""
        from woofalytics.audio.devices import find_microphone

        mic = find_microphone(device_name="ReSpeaker")

        assert mic is not None
        assert "ReSpeaker" in mic.name

    def test_not_found(self, mock_pyaudio):
        """Test error when microphone not found."""
        from woofalytics.audio.devices import find_microphone

        with pytest.raises(RuntimeError, match="No microphone matching"):
            find_microphone(device_name="NonExistent")
