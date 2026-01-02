"""Async audio capture with ring buffer.

This module provides an async wrapper around PyAudio for non-blocking
audio capture suitable for use with FastAPI and asyncio.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import structlog

from woofalytics.audio.devices import find_microphone, set_microphone_volume, MicrophoneInfo
from woofalytics.config import AudioConfig

if TYPE_CHECKING:
    import pyaudio

logger = structlog.get_logger(__name__)


@dataclass
class AudioFrame:
    """A single frame of captured audio data."""

    timestamp: float
    data: bytes
    channels: int
    sample_rate: int

    def to_numpy(self) -> np.ndarray:
        """Convert raw bytes to numpy array.

        Returns:
            Array of shape (channels, samples) with int16 values.
        """
        arr = np.frombuffer(self.data, dtype=np.int16)
        # Reshape from interleaved to (channels, samples)
        return arr.reshape((self.channels, -1), order="F")

    @property
    def duration_ms(self) -> float:
        """Duration of this frame in milliseconds."""
        samples = len(self.data) // (2 * self.channels)  # 2 bytes per int16
        return (samples / self.sample_rate) * 1000


@dataclass
class AsyncAudioCapture:
    """Async audio capture with ring buffer.

    This class runs PyAudio capture in a background thread and provides
    an async interface for reading audio frames.

    Attributes:
        config: Audio configuration settings.
        buffer_seconds: Size of the ring buffer in seconds.
    """

    config: AudioConfig
    buffer_seconds: float = 30.0

    # Private attributes
    _microphone: MicrophoneInfo | None = field(default=None, init=False)
    _buffer: deque[AudioFrame] = field(default_factory=deque, init=False)
    _buffer_lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _running: bool = field(default=False, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)
    _error: Exception | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        # Calculate max buffer size based on buffer_seconds
        frames_per_second = self.config.sample_rate / self.config.chunk_size
        max_frames = int(frames_per_second * self.buffer_seconds)
        self._buffer = deque(maxlen=max_frames)

    async def start(self) -> None:
        """Start audio capture in background thread.

        Raises:
            RuntimeError: If capture is already running or no microphone found.
        """
        if self._running:
            raise RuntimeError("Audio capture is already running")

        # Find microphone
        self._microphone = find_microphone(
            device_name=self.config.device_name,
            min_channels=self.config.channels,
        )

        # Set volume
        set_microphone_volume(self.config.volume_percent)

        # Start capture thread
        self._running = True
        self._error = None
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="AudioCapture",
            daemon=True,
        )
        self._thread.start()

        # Wait briefly to check for startup errors
        await asyncio.sleep(0.1)
        if self._error:
            raise self._error

        logger.info(
            "audio_capture_started",
            device=self._microphone.name,
            sample_rate=self.config.sample_rate,
            channels=self.config.channels,
        )

    async def stop(self) -> None:
        """Stop audio capture and wait for thread to finish."""
        if not self._running:
            return

        self._running = False

        if self._thread and self._thread.is_alive():
            # Wait for thread to finish with timeout
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._thread.join, 2.0)

        logger.info("audio_capture_stopped")

    def _capture_loop(self) -> None:
        """Main capture loop running in background thread."""
        import pyaudio

        p: pyaudio.PyAudio | None = None
        stream: pyaudio.Stream | None = None

        try:
            p = pyaudio.PyAudio()
            stream = p.open(
                format=pyaudio.paInt16,
                channels=self.config.channels,
                rate=self.config.sample_rate,
                frames_per_buffer=self.config.chunk_size,
                input=True,
                input_device_index=self._microphone.index if self._microphone else None,
            )

            logger.debug("audio_stream_opened")

            while self._running:
                try:
                    data = stream.read(self.config.chunk_size, exception_on_overflow=False)

                    frame = AudioFrame(
                        timestamp=time.time(),
                        data=data,
                        channels=self.config.channels,
                        sample_rate=self.config.sample_rate,
                    )

                    with self._buffer_lock:
                        self._buffer.append(frame)

                except OSError as e:
                    logger.warning("audio_read_error", error=str(e))
                    # Try to recover by reopening stream
                    if stream:
                        stream.stop_stream()
                        stream.close()

                    stream = p.open(
                        format=pyaudio.paInt16,
                        channels=self.config.channels,
                        rate=self.config.sample_rate,
                        frames_per_buffer=self.config.chunk_size,
                        input=True,
                        input_device_index=self._microphone.index if self._microphone else None,
                    )

        except Exception as e:
            logger.error("audio_capture_error", error=str(e))
            self._error = e

        finally:
            if stream:
                stream.stop_stream()
                stream.close()
            if p:
                p.terminate()

    def get_recent_frames(self, count: int | None = None) -> list[AudioFrame]:
        """Get recent audio frames from the buffer.

        Args:
            count: Number of frames to return. None = all frames.

        Returns:
            List of AudioFrame objects (oldest first).
        """
        with self._buffer_lock:
            if count is None:
                return list(self._buffer)
            return list(self._buffer)[-count:]

    def get_frames_since(self, timestamp: float) -> list[AudioFrame]:
        """Get all frames captured since the given timestamp.

        Args:
            timestamp: Unix timestamp (from time.time()).

        Returns:
            List of AudioFrame objects captured after timestamp.
        """
        with self._buffer_lock:
            return [f for f in self._buffer if f.timestamp >= timestamp]

    def get_buffer_as_array(
        self,
        seconds: float | None = None,
    ) -> tuple[np.ndarray, float]:
        """Get buffered audio as a numpy array.

        Args:
            seconds: Number of seconds to return. None = entire buffer.

        Returns:
            Tuple of (audio_array, start_timestamp).
            Array shape is (channels, samples).
        """
        with self._buffer_lock:
            frames = list(self._buffer)

        if not frames:
            return np.array([], dtype=np.int16), time.time()

        if seconds is not None:
            # Calculate how many frames we need
            frames_per_second = self.config.sample_rate / self.config.chunk_size
            frame_count = int(frames_per_second * seconds)
            frames = frames[-frame_count:]

        # Concatenate all frame data
        arrays = [f.to_numpy() for f in frames]
        combined = np.concatenate(arrays, axis=1)

        return combined, frames[0].timestamp

    @property
    def is_running(self) -> bool:
        """Check if capture is currently running."""
        return self._running

    @property
    def microphone(self) -> MicrophoneInfo | None:
        """Get the currently selected microphone."""
        return self._microphone

    @property
    def buffer_size(self) -> int:
        """Get current number of frames in buffer."""
        with self._buffer_lock:
            return len(self._buffer)
