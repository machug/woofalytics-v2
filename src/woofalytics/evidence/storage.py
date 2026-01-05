"""Evidence storage and recording management.

This module handles recording bark audio clips to disk with
structured metadata for council complaints and legal documentation.
"""

from __future__ import annotations

import asyncio
import json
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles
import aiofiles.os
import numpy as np
import structlog

from woofalytics.config import EvidenceConfig
from woofalytics.evidence.metadata import EvidenceMetadata, EvidenceIndex

if TYPE_CHECKING:
    from woofalytics.audio.capture import AsyncAudioCapture
    from woofalytics.detection.model import BarkEvent

# Callback type: (evidence_filename, first_bark_time, last_bark_time) -> None
EvidenceSavedCallback = Callable[[str, datetime, datetime], None]

logger = structlog.get_logger(__name__)


@dataclass
class PendingRecording:
    """A recording that is being captured."""

    trigger_event: BarkEvent
    start_time: float
    events: list[BarkEvent] = field(default_factory=list)


@dataclass
class EvidenceStorage:
    """Manages evidence recording and storage.

    This class handles:
    - Recording audio clips with past/future context
    - Saving WAV files with timestamps
    - Creating JSON metadata sidecars
    - Maintaining an evidence index
    """

    config: EvidenceConfig
    audio_capture: AsyncAudioCapture
    microphone_name: str = "Unknown"

    # Private state
    _index: EvidenceIndex = field(default_factory=EvidenceIndex, init=False)
    _pending: PendingRecording | None = field(default=None, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _on_saved_callbacks: list[EvidenceSavedCallback] = field(default_factory=list, init=False)

    def add_on_saved_callback(self, callback: EvidenceSavedCallback) -> None:
        """Register a callback to be called when evidence is saved.

        Args:
            callback: Function called with (filename, first_bark_time, last_bark_time).
        """
        self._on_saved_callbacks.append(callback)

    def __post_init__(self) -> None:
        """Initialize storage directory and load index."""
        self.config.directory.mkdir(parents=True, exist_ok=True)
        self._load_index()

    def _load_index(self) -> None:
        """Load the evidence index from disk."""
        index_path = self.config.directory / "index.json"

        if index_path.exists():
            try:
                with open(index_path) as f:
                    data = json.load(f)
                self._index = EvidenceIndex.from_dict(data)
                logger.info(
                    "evidence_index_loaded",
                    count=len(self._index.entries),
                )
            except Exception as e:
                logger.warning("evidence_index_load_error", error=str(e))
                self._index = EvidenceIndex()
        else:
            self._index = EvidenceIndex()

    async def _save_index(self) -> None:
        """Save the evidence index to disk."""
        index_path = self.config.directory / "index.json"

        try:
            async with aiofiles.open(index_path, "w") as f:
                await f.write(json.dumps(self._index.to_dict(), indent=2))
        except Exception as e:
            logger.error("evidence_index_save_error", error=str(e))

    async def on_bark_event(self, event: BarkEvent) -> None:
        """Handle a bark detection event.

        This method should be registered as a callback on the BarkDetector.
        It manages the recording lifecycle:
        - Starts recording on first bark
        - Extends recording on subsequent barks
        - Saves when future context window expires

        Args:
            event: The bark detection event.
        """
        async with self._lock:
            if event.is_barking:
                if self._pending is None:
                    # Start new recording
                    self._pending = PendingRecording(
                        trigger_event=event,
                        start_time=event.timestamp.timestamp(),
                    )
                    logger.info("evidence_recording_started")

                # Track this bark event
                if self._pending:
                    self._pending.events.append(event)

    async def check_and_save(self) -> EvidenceMetadata | None:
        """Check if pending recording should be saved.

        This should be called periodically (e.g., every second) to
        check if the future context window has expired.

        Returns:
            EvidenceMetadata if a recording was saved, None otherwise.
        """
        async with self._lock:
            if self._pending is None:
                return None

            # Get the last bark event time
            if not self._pending.events:
                return None

            last_bark_time = max(e.timestamp.timestamp() for e in self._pending.events)
            now = datetime.now().timestamp()

            # Check if future context window has expired
            if now - last_bark_time >= self.config.future_context_seconds:
                metadata = await self._save_recording()
                self._pending = None
                return metadata

        return None

    async def _save_recording(self) -> EvidenceMetadata | None:
        """Save the pending recording to disk.

        Returns:
            EvidenceMetadata for the saved recording.
        """
        if self._pending is None:
            return None

        try:
            # Calculate time range for the recording
            trigger_time = self._pending.trigger_event.timestamp.timestamp()
            last_bark_time = max(e.timestamp.timestamp() for e in self._pending.events)

            start_time = trigger_time - self.config.past_context_seconds
            end_time = last_bark_time + self.config.future_context_seconds

            # Get audio data from buffer
            audio_data, actual_start = self.audio_capture.get_buffer_as_array(
                seconds=end_time - start_time + 5  # Extra buffer
            )

            if audio_data.size == 0:
                logger.warning("evidence_no_audio_data")
                return None

            # Generate filename with timestamp
            timestamp_str = self._pending.trigger_event.timestamp.strftime("%Y-%m-%d_%H-%M-%S")
            wav_filename = f"{timestamp_str}_bark.wav"
            json_filename = f"{timestamp_str}_bark.json"

            wav_path = self.config.directory / wav_filename
            json_path = self.config.directory / json_filename

            # Calculate recording stats
            duration_seconds = audio_data.shape[1] / self.audio_capture.config.sample_rate
            peak_probability = max(e.probability for e in self._pending.events)
            bark_count = len(self._pending.events)

            # Get DOA from trigger event
            doa_bartlett = self._pending.trigger_event.doa_bartlett
            doa_capon = self._pending.trigger_event.doa_capon
            doa_mem = self._pending.trigger_event.doa_mem

            # Save WAV file (run in executor since wave is blocking)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._write_wav,
                wav_path,
                audio_data,
                self.audio_capture.config.sample_rate,
                self.audio_capture.config.channels,
            )

            # Create metadata
            metadata = EvidenceMetadata.create(
                filename=wav_filename,
                duration_seconds=duration_seconds,
                sample_rate=self.audio_capture.config.sample_rate,
                channels=self.audio_capture.config.channels,
                trigger_probability=self._pending.trigger_event.probability,
                peak_probability=peak_probability,
                bark_count=bark_count,
                microphone_name=self.microphone_name,
                doa_bartlett=doa_bartlett,
                doa_capon=doa_capon,
                doa_mem=doa_mem,
            )

            # Save metadata JSON
            async with aiofiles.open(json_path, "w") as f:
                await f.write(json.dumps(metadata.to_dict(), indent=2))

            # Update index
            self._index.add(metadata)
            await self._save_index()

            logger.info(
                "evidence_saved",
                filename=wav_filename,
                duration=f"{duration_seconds:.1f}s",
                barks=bark_count,
                peak_prob=f"{peak_probability:.3f}",
            )

            # Notify callbacks with bark time range for fingerprint linking
            # Run callbacks in executor to avoid blocking the event loop
            first_bark = self._pending.trigger_event.timestamp
            last_bark = max(e.timestamp for e in self._pending.events)
            loop = asyncio.get_event_loop()
            for callback in self._on_saved_callbacks:
                try:
                    await loop.run_in_executor(
                        None,
                        callback,
                        wav_filename,
                        first_bark,
                        last_bark,
                    )
                except Exception as cb_err:
                    logger.warning("evidence_callback_error", error=str(cb_err))

            return metadata

        except Exception as e:
            logger.error("evidence_save_error", error=str(e))
            return None

    @staticmethod
    def _write_wav(
        path: Path,
        audio: np.ndarray,
        sample_rate: int,
        channels: int,
    ) -> None:
        """Write audio array to WAV file.

        Args:
            path: Path to save the WAV file.
            audio: Audio array of shape (channels, samples).
            sample_rate: Sample rate in Hz.
            channels: Number of channels.
        """
        # Convert float to int16 if needed
        if audio.dtype == np.float32 or audio.dtype == np.float64:
            audio = (audio * 32767).astype(np.int16)

        # Interleave channels: (channels, samples) -> (samples * channels,)
        interleaved = audio.T.flatten()

        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(sample_rate)
            wav.writeframes(interleaved.tobytes())

    def get_recent_evidence(self, count: int = 10) -> list[EvidenceMetadata]:
        """Get most recent evidence recordings.

        Args:
            count: Number of recordings to return.

        Returns:
            List of EvidenceMetadata for recent recordings.
        """
        return self._index.get_recent(count)

    def get_evidence_by_date(
        self,
        start: datetime,
        end: datetime,
    ) -> list[EvidenceMetadata]:
        """Get evidence within a date range.

        Args:
            start: Start of date range.
            end: End of date range.

        Returns:
            List of EvidenceMetadata within the range.
        """
        return self._index.get_by_date_range(start, end)

    @property
    def total_recordings(self) -> int:
        """Get total number of evidence recordings."""
        return len(self._index.entries)

    @property
    def total_duration_seconds(self) -> float:
        """Get total duration of all recordings."""
        return self._index.total_duration_seconds

    @property
    def total_barks_recorded(self) -> int:
        """Get total bark count across all recordings."""
        return self._index.total_bark_count

    def get_stats(self) -> dict:
        """Get evidence storage statistics."""
        return {
            "total_recordings": self.total_recordings,
            "total_duration_seconds": self.total_duration_seconds,
            "total_barks_recorded": self.total_barks_recorded,
            "storage_directory": str(self.config.directory),
        }

    async def cleanup_old_evidence(self, max_age_days: int = 90) -> int:
        """Remove evidence files older than max_age_days.

        Args:
            max_age_days: Maximum age of evidence to keep.

        Returns:
            Number of files removed.
        """
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=max_age_days)
        removed = 0

        async with self._lock:
            entries_to_keep = []

            for entry in self._index.entries:
                if entry.timestamp_local.replace(tzinfo=None) < cutoff:
                    # Remove files
                    wav_path = self.config.directory / entry.filename
                    json_path = self.config.directory / entry.filename.replace(".wav", ".json")

                    try:
                        if wav_path.exists():
                            await aiofiles.os.remove(wav_path)
                        if json_path.exists():
                            await aiofiles.os.remove(json_path)
                        removed += 1
                        logger.info("evidence_removed", filename=entry.filename)
                    except Exception as e:
                        logger.warning("evidence_removal_error", filename=entry.filename, error=str(e))
                        entries_to_keep.append(entry)  # Keep if removal failed
                else:
                    entries_to_keep.append(entry)

            self._index.entries = entries_to_keep
            await self._save_index()

        logger.info("evidence_cleanup_complete", removed=removed)
        return removed

    async def purge_evidence(
        self,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> int:
        """Purge evidence files matching criteria.

        Args:
            before: Delete recordings before this timestamp.
            after: Delete recordings after this timestamp.

        Returns:
            Number of files removed.
        """
        removed = 0

        async with self._lock:
            entries_to_keep = []

            for entry in self._index.entries:
                entry_ts = entry.timestamp_local.replace(tzinfo=None)
                should_delete = False

                if before is not None and after is not None:
                    # Delete within range
                    should_delete = after.replace(tzinfo=None) <= entry_ts < before.replace(tzinfo=None)
                elif before is not None:
                    should_delete = entry_ts < before.replace(tzinfo=None)
                elif after is not None:
                    should_delete = entry_ts >= after.replace(tzinfo=None)

                if should_delete:
                    wav_path = self.config.directory / entry.filename
                    json_path = self.config.directory / entry.filename.replace(".wav", ".json")
                    # Also remove cached opus file if it exists
                    opus_path = self.config.directory / ".cache" / entry.filename.replace(".wav", ".opus")

                    try:
                        if wav_path.exists():
                            await aiofiles.os.remove(wav_path)
                        if json_path.exists():
                            await aiofiles.os.remove(json_path)
                        if opus_path.exists():
                            await aiofiles.os.remove(opus_path)
                        removed += 1
                        logger.info("evidence_purged", filename=entry.filename)
                    except Exception as e:
                        logger.warning("evidence_purge_error", filename=entry.filename, error=str(e))
                        entries_to_keep.append(entry)
                else:
                    entries_to_keep.append(entry)

            self._index.entries = entries_to_keep
            await self._save_index()

        logger.info("evidence_purge_complete", removed=removed)
        return removed

    async def purge_all_evidence(self) -> int:
        """Delete ALL evidence files. Use with caution.

        Returns:
            Number of files removed.
        """
        removed = 0

        async with self._lock:
            for entry in self._index.entries:
                wav_path = self.config.directory / entry.filename
                json_path = self.config.directory / entry.filename.replace(".wav", ".json")
                opus_path = self.config.directory / ".cache" / entry.filename.replace(".wav", ".opus")

                try:
                    if wav_path.exists():
                        await aiofiles.os.remove(wav_path)
                    if json_path.exists():
                        await aiofiles.os.remove(json_path)
                    if opus_path.exists():
                        await aiofiles.os.remove(opus_path)
                    removed += 1
                except Exception as e:
                    logger.warning("evidence_purge_error", filename=entry.filename, error=str(e))

            self._index.entries = []
            await self._save_index()

        logger.warning("all_evidence_purged", removed=removed)
        return removed
