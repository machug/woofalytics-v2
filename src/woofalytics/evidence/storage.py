"""Evidence storage and recording management.

This module handles recording bark audio clips to disk with
structured metadata for council complaints and legal documentation.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    # Set on a continuation clip: audio starts where the previous clip ended
    # (instead of trigger - past_context_seconds).
    clip_start: float | None = None
    # Last bark of the previous clip. Sets the future-context deadline of a
    # continuation, but is not counted as a detection in this clip.
    carried_last_bark: BarkEvent | None = None

    def last_bark(self) -> BarkEvent:
        candidates = self.events + ([self.carried_last_bark] if self.carried_last_bark else [])
        return max(candidates, key=lambda e: e.timestamp)

    def audio_start(self, past_context_seconds: float) -> float:
        if self.clip_start is not None:
            return self.clip_start
        return self.start_time - past_context_seconds


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
                # Keep the broken file for inspection, then rebuild from sidecars
                # so a corrupt index never makes existing clips disappear.
                broken = index_path.with_name(f"index.broken-{int(time.time())}.json")
                index_path.rename(broken)
                logger.error("evidence_index_load_error", error=str(e), moved_to=broken.name)
                self._index = self._rebuild_index()
        else:
            self._index = self._rebuild_index()

    def _rebuild_index(self) -> EvidenceIndex:
        """Build the index from the JSON sidecar next to each WAV."""
        index = EvidenceIndex()
        for json_path in sorted(self.config.directory.glob("*_bark*.json")):
            try:
                index.entries.append(EvidenceMetadata.from_dict(json.loads(json_path.read_text())))
            except Exception as e:
                logger.warning("evidence_sidecar_unreadable", file=json_path.name, error=str(e))
        if index.entries:
            logger.warning("evidence_index_rebuilt", count=len(index.entries))
            self._atomic_write(self.config.directory / "index.json", json.dumps(index.to_dict(), indent=2))
        return index

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        """Write text so a crash leaves either the old or the new file, never half of one."""
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def _audit(self, action: str, **fields: object) -> None:
        """Append one line to evidence/audit.log (JSON lines).

        ponytail: append-only by convention, not cryptographically chained.
        Hashes in it let anyone check a WAV was not changed; upgrade to a
        hash-chained log if someone needs to prove the log itself is complete.
        """
        entry = {"time_utc": datetime.now(timezone.utc).isoformat(), "action": action, **fields}
        try:
            with open(self.config.directory / "audit.log", "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error("evidence_audit_write_error", error=str(e))

    async def _save_index(self) -> None:
        """Save the evidence index to disk atomically."""
        index_path = self.config.directory / "index.json"
        text = json.dumps(self._index.to_dict(), indent=2)
        try:
            await asyncio.get_running_loop().run_in_executor(None, self._atomic_write, index_path, text)
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
            if not self._pending.events and self._pending.carried_last_bark is None:
                return None

            last_bark_time = self._pending.last_bark().timestamp.timestamp()
            clip_start = self._pending.audio_start(self.config.past_context_seconds)
            now = time.time()

            # Save when barking has stopped for future_context_seconds, or when
            # the clip reaches max_clip_seconds (a long episode is split; the
            # next bark starts a new clip with its own past context).
            quiet_long_enough = now - last_bark_time >= self.config.future_context_seconds
            clip_full = now - clip_start >= self.config.max_clip_seconds
            if quiet_long_enough or clip_full:
                previous = self._pending
                metadata = await self._save_recording()
                self._pending = None
                if not quiet_long_enough and metadata and metadata.recording_end_utc:
                    # Episode still inside its future-context window: continue
                    # seamlessly so the trailing context is not lost.
                    last = previous.last_bark()
                    self._pending = PendingRecording(
                        trigger_event=last,
                        start_time=last.timestamp.timestamp(),
                        carried_last_bark=last,
                        clip_start=metadata.recording_end_utc.timestamp(),
                    )
                    logger.info("evidence_clip_continued", previous=metadata.filename)
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
            last_bark_time = self._pending.last_bark().timestamp.timestamp()

            start_time = self._pending.audio_start(self.config.past_context_seconds)
            end_time = min(last_bark_time + self.config.future_context_seconds, time.time())

            # Get exactly this time window from the buffer
            audio_data, rec_start, rec_end = self.audio_capture.get_audio_between(start_time, end_time)

            if audio_data.size == 0:
                logger.warning("evidence_no_audio_data")
                return None

            if self._pending.clip_start is None and rec_start > trigger_time:
                # Should not happen with a correctly sized buffer; flag it loudly.
                logger.error("evidence_trigger_not_in_clip", missing_seconds=round(rec_start - trigger_time, 1))

            # Filename: trigger time in UTC (the sidecar holds local time too).
            # A numeric suffix avoids overwriting a clip saved in the same second.
            timestamp_str = self._pending.trigger_event.timestamp.astimezone(timezone.utc).strftime(
                "%Y-%m-%d_%H-%M-%S"
            )
            suffix = ""
            n = 1
            while (self.config.directory / f"{timestamp_str}_bark{suffix}.wav").exists():
                n += 1
                suffix = f"-{n}"
            wav_filename = f"{timestamp_str}_bark{suffix}.wav"
            json_filename = f"{timestamp_str}_bark{suffix}.json"

            wav_path = self.config.directory / wav_filename
            json_path = self.config.directory / json_filename

            # Calculate recording stats
            duration_seconds = audio_data.shape[1] / self.audio_capture.config.sample_rate
            peak_probability = max((e.probability for e in self._pending.events), default=0.0)
            bark_count = len(self._pending.events)

            # Get DOA from trigger event
            doa_bartlett = self._pending.trigger_event.doa_bartlett
            doa_capon = self._pending.trigger_event.doa_capon
            doa_mem = self._pending.trigger_event.doa_mem

            # Save WAV file (run in executor since wave is blocking)
            loop = asyncio.get_event_loop()
            sha256 = await loop.run_in_executor(
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
                timestamp_utc=self._pending.trigger_event.timestamp,
                recording_start_utc=datetime.fromtimestamp(rec_start, timezone.utc),
                recording_end_utc=datetime.fromtimestamp(rec_end, timezone.utc),
                sha256=sha256,
            )

            # Save metadata JSON
            await loop.run_in_executor(
                None, self._atomic_write, json_path, json.dumps(metadata.to_dict(), indent=2)
            )
            self._audit("saved", filename=wav_filename, sha256=sha256)

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
            last_bark = self._pending.last_bark().timestamp
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
    ) -> str:
        """Write audio array to WAV file and return its SHA-256 hex digest.

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

        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()

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
                        self._audit("deleted", filename=entry.filename, sha256=entry.sha256, via="purge")
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
                    self._audit("deleted", filename=entry.filename, sha256=entry.sha256, via="purge_all")
                except Exception as e:
                    logger.warning("evidence_purge_error", filename=entry.filename, error=str(e))

            self._index.entries = []
            await self._save_index()

        logger.warning("all_evidence_purged", removed=removed)
        return removed
