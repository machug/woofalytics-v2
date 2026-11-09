"""Checks for evidence recording: long episodes, timing, hashes, index safety."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import numpy as np

from woofalytics.audio.capture import AsyncAudioCapture, AudioFrame
from woofalytics.config import AudioConfig, EvidenceConfig
from woofalytics.detection.model import BarkEvent
from woofalytics.evidence import storage as storage_mod
from woofalytics.evidence.storage import EvidenceStorage

RATE, CHUNK, CH = 8000, 800, 4  # 10 frames per second keeps the test small
T0 = 1_800_000_000.0  # trigger time (unix)


def _capture(seconds_before: float, seconds_after: float) -> AsyncAudioCapture:
    cap = AsyncAudioCapture(config=AudioConfig(sample_rate=RATE, chunk_size=CHUNK, channels=CH), buffer_seconds=600)
    t = T0 - seconds_before
    while t < T0 + seconds_after:
        t += CHUNK / RATE
        data = np.full((CHUNK, CH), int(t) % 1000, dtype=np.int16).tobytes()
        cap._buffer.append(AudioFrame(timestamp=t, data=data, channels=CH, sample_rate=RATE))
    return cap


def _bark(t: float) -> BarkEvent:
    return BarkEvent(timestamp=datetime.fromtimestamp(t, timezone.utc), probability=0.9, is_barking=True)


async def test_long_episode_is_split_and_keeps_trigger(tmp_path, monkeypatch):
    cfg = EvidenceConfig(directory=tmp_path, past_context_seconds=5, future_context_seconds=5, max_clip_seconds=30)
    store = EvidenceStorage(config=cfg, audio_capture=_capture(60, 120))

    for i in range(0, 100):  # barking every second for 100 s
        await store.on_bark_event(_bark(T0 + i))

    monkeypatch.setattr(storage_mod.time, "time", lambda: T0 + 20)
    assert await store.check_and_save() is None  # still barking, clip not full

    monkeypatch.setattr(storage_mod.time, "time", lambda: T0 + 26)  # clip now 31 s long
    meta = await store.check_and_save()
    assert meta is not None

    # Clip starts at trigger - past context, so the trigger bark is inside it.
    assert meta.recording_start_utc.timestamp() <= T0 - 4.9
    assert meta.recording_end_utc.timestamp() <= T0 + 26 + CHUNK / RATE + 1e-6  # whole chunks only
    assert 30 <= meta.duration_seconds <= 31.2
    # Timestamp is the bark time, not the save time.
    assert meta.timestamp_utc.timestamp() == T0

    wav = tmp_path / meta.filename
    assert hashlib.sha256(wav.read_bytes()).hexdigest() == meta.sha256
    audit = [json.loads(line) for line in (tmp_path / "audit.log").read_text().splitlines()]
    assert audit[-1]["action"] == "saved" and audit[-1]["sha256"] == meta.sha256


async def test_corrupt_index_is_rebuilt_from_sidecars(tmp_path, monkeypatch):
    cfg = EvidenceConfig(directory=tmp_path, past_context_seconds=5, future_context_seconds=5)
    store = EvidenceStorage(config=cfg, audio_capture=_capture(30, 30))
    await store.on_bark_event(_bark(T0))
    monkeypatch.setattr(storage_mod.time, "time", lambda: T0 + 6)
    assert await store.check_and_save() is not None

    (tmp_path / "index.json").write_text('{"entries": [')  # simulate crash mid-write

    reloaded = EvidenceStorage(config=cfg, audio_capture=store.audio_capture)
    assert reloaded.total_recordings == 1
    assert list(tmp_path.glob("index.broken-*.json"))


def test_channel_selection_keeps_raw_mics():
    cfg = AudioConfig(sample_rate=RATE, chunk_size=64, channels=4, device_channels=6, channel_indices=[1, 2, 3, 4])
    cap = AsyncAudioCapture(config=cfg)
    raw = np.array([[0, 1, 2, 3, 4, 5], [10, 11, 12, 13, 14, 15]], dtype=np.int16).tobytes()
    out = np.frombuffer(cap._select_channels(raw), dtype=np.int16).reshape(-1, 4)
    assert out.tolist() == [[1, 2, 3, 4], [11, 12, 13, 14]]


async def test_split_continues_until_future_context_ends(tmp_path, monkeypatch):
    cfg = EvidenceConfig(directory=tmp_path, past_context_seconds=5, future_context_seconds=5, max_clip_seconds=30)
    store = EvidenceStorage(config=cfg, audio_capture=_capture(60, 120))
    for i in range(0, 25):  # last bark at T0+24, so audio is wanted until T0+29
        await store.on_bark_event(_bark(T0 + i))

    monkeypatch.setattr(storage_mod.time, "time", lambda: T0 + 26)
    first = await store.check_and_save()
    monkeypatch.setattr(storage_mod.time, "time", lambda: T0 + 30)
    second = await store.check_and_save()

    assert first is not None and second is not None
    # Continuation starts where the first clip ended and covers the rest of the window.
    assert second.recording_start_utc.timestamp() >= first.recording_end_utc.timestamp() - 1e-6
    assert second.recording_end_utc.timestamp() >= T0 + 29
    # No barks fall inside the continuation, so none are counted twice.
    assert first.detection.bark_count_in_clip == 25
    assert second.detection.bark_count_in_clip == 0


def test_device_channels_without_selection_is_rejected():
    import pytest

    with pytest.raises(ValueError, match="channel_indices is required"):
        AudioConfig(channels=4, device_channels=6)


async def test_stop_interrupts_retry_backoff():
    import threading
    import time as _time

    cap = AsyncAudioCapture(config=AudioConfig(sample_rate=RATE, chunk_size=CHUNK, channels=CH))
    cap._running = True
    cap._thread = threading.Thread(target=lambda: cap._stop_event.wait(30), daemon=True)
    cap._thread.start()
    t = _time.monotonic()
    await cap.stop()
    assert not cap._thread.is_alive() and _time.monotonic() - t < 1.0
