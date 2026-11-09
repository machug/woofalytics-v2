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
    _last_frame_time: float = field(default=0.0, init=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)

    # Seconds without a new frame before capture counts as stalled.
    STALL_SECONDS = 5.0

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
        if self._thread and self._thread.is_alive():
            raise RuntimeError("Previous audio capture thread has not exited yet")

        # Find microphone
        self._microphone = find_microphone(
            device_name=self.config.device_name,
            min_channels=self._open_channels,
        )

        # Set volume
        set_microphone_volume(self.config.volume_percent)

        # Start capture thread
        self._running = True
        self._stop_event.clear()
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
        self._stop_event.set()  # wakes a retry backoff immediately

        if self._thread and self._thread.is_alive():
            # Wait for thread to finish with timeout
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._thread.join, 2.0)

        logger.info("audio_capture_stopped")

    @property
    def _open_channels(self) -> int:
        """Channels to open on the device (may be more than we keep)."""
        return self.config.device_channels or self.config.channels

    def _select_channels(self, data: bytes) -> bytes:
        """Keep only config.channel_indices from interleaved int16 data."""
        if self.config.channel_indices is None:
            return data
        arr = np.frombuffer(data, dtype=np.int16).reshape(-1, self._open_channels)
        return np.ascontiguousarray(arr[:, self.config.channel_indices]).tobytes()

    def _open_stream(self, p: pyaudio.PyAudio) -> pyaudio.Stream:
        import pyaudio

        return p.open(
            format=pyaudio.paInt16,
            channels=self._open_channels,
            rate=self.config.sample_rate,
            frames_per_buffer=self.config.chunk_size,
            input=True,
            input_device_index=self._microphone.index if self._microphone else None,
        )

    def _capture_loop(self) -> None:
        """Main capture loop running in background thread.

        Read errors (e.g. USB mic unplugged) do not end the loop: the
        stream is reopened with backoff until it works or stop() is called.
        Only a failure on the very first open is fatal (reported to start()).
        """
        import pyaudio

        p: pyaudio.PyAudio | None = None
        stream: pyaudio.Stream | None = None

        try:
            p = pyaudio.PyAudio()
            stream = self._open_stream(p)
            logger.debug("audio_stream_opened")
        except Exception as e:
            logger.error("audio_capture_error", error=str(e))
            self._error = e
            if p:
                p.terminate()
            return

        backoff = 1.0
        try:
            while self._running:
                try:
                    if stream is None:
                        stream = self._open_stream(p)
                        logger.info("audio_stream_reopened")
                        backoff = 1.0
                    data = stream.read(self.config.chunk_size, exception_on_overflow=False)
                    now = time.time()
                    frame = AudioFrame(
                        timestamp=now,
                        data=self._select_channels(data),
                        channels=self.config.channels,
                        sample_rate=self.config.sample_rate,
                    )
                    with self._buffer_lock:
                        self._buffer.append(frame)
                    self._last_frame_time = now

                except Exception as e:
                    logger.error("audio_read_error", error=str(e), retry_in=backoff)
                    if stream:
                        try:
                            stream.stop_stream()
                            stream.close()
                        except Exception:
                            pass
                        stream = None
                    self._stop_event.wait(backoff)
                    backoff = min(backoff * 2, 30.0)
        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
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

    def get_audio_between(
        self,
        start: float,
        end: float,
    ) -> tuple[np.ndarray, float, float]:
        """Get buffered audio for a wall-clock window.

        Args:
            start: Unix timestamp of the window start.
            end: Unix timestamp of the window end.

        Returns:
            Tuple of (audio_array, first_frame_start, last_frame_end).
            Array shape is (channels, samples). Empty array if no frames.
            Frame timestamps mark the end of each chunk.
        """
        frame_s = self.config.chunk_size / self.config.sample_rate
        with self._buffer_lock:
            frames = [f for f in self._buffer if start < f.timestamp and f.timestamp - frame_s <= end]

        if not frames:
            return np.array([], dtype=np.int16), start, start

        combined = np.concatenate([f.to_numpy() for f in frames], axis=1)
        return combined, frames[0].timestamp - frame_s, frames[-1].timestamp

    @property
    def is_running(self) -> bool:
        """Check if capture is currently running."""
        return self._running

    @property
    def is_healthy(self) -> bool:
        """True when the capture thread is alive and frames are still arriving."""
        return (
            self._running
            and self._thread is not None
            and self._thread.is_alive()
            and time.time() - self._last_frame_time < self.STALL_SECONDS
        )

    @property
    def microphone(self) -> MicrophoneInfo | None:
        """Get the currently selected microphone."""
        return self._microphone

    @property
    def buffer_size(self) -> int:
        """Get current number of frames in buffer."""
        with self._buffer_lock:
            return len(self._buffer)
