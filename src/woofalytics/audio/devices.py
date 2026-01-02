"""Microphone device discovery and selection.

This module provides flexible microphone detection that works with
various USB microphone arrays, not just the Andrea PureAudio.

Supported devices:
- Andrea PureAudio USB Array
- ReSpeaker 2-Mic HAT
- ReSpeaker 4-Mic Array
- Any USB microphone with 2+ channels
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import pyaudio

logger = structlog.get_logger(__name__)


@dataclass
class MicrophoneInfo:
    """Information about an audio input device."""

    index: int
    name: str
    channels: int
    sample_rate: int
    is_default: bool = False

    def __str__(self) -> str:
        default_marker = " (default)" if self.is_default else ""
        return f"[{self.index}] {self.name} ({self.channels}ch, {self.sample_rate}Hz){default_marker}"


def list_microphones(min_channels: int = 1) -> list[MicrophoneInfo]:
    """List all available input devices with at least min_channels.

    Args:
        min_channels: Minimum number of input channels required.

    Returns:
        List of MicrophoneInfo objects for matching devices.
    """
    import pyaudio

    p = pyaudio.PyAudio()
    devices: list[MicrophoneInfo] = []

    try:
        host_api_info = p.get_host_api_info_by_index(0)
        device_count = int(host_api_info.get("deviceCount", 0))
        default_input = int(host_api_info.get("defaultInputDevice", -1))

        for i in range(device_count):
            try:
                info = p.get_device_info_by_index(i)
                max_channels = int(info.get("maxInputChannels", 0))

                if max_channels >= min_channels:
                    devices.append(
                        MicrophoneInfo(
                            index=i,
                            name=str(info.get("name", f"Device {i}")),
                            channels=max_channels,
                            sample_rate=int(info.get("defaultSampleRate", 44100)),
                            is_default=(i == default_input),
                        )
                    )
            except Exception as e:
                logger.warning("error_reading_device", index=i, error=str(e))
                continue

    finally:
        p.terminate()

    return devices


def find_microphone(
    device_name: str | None = None,
    min_channels: int = 2,
) -> MicrophoneInfo:
    """Find a suitable microphone device.

    Args:
        device_name: Optional device name filter (case-insensitive substring match).
                    If None, returns first device with min_channels.
        min_channels: Minimum required input channels.

    Returns:
        MicrophoneInfo for the selected device.

    Raises:
        RuntimeError: If no suitable microphone is found.

    Examples:
        >>> mic = find_microphone()  # Auto-detect any 2+ channel mic
        >>> mic = find_microphone("Andrea")  # Find Andrea microphone
        >>> mic = find_microphone("ReSpeaker", min_channels=2)
    """
    devices = list_microphones(min_channels=min_channels)

    if not devices:
        raise RuntimeError(
            f"No microphone found with at least {min_channels} channels. "
            "Please check your audio device connections."
        )

    # If device_name specified, filter by name
    if device_name:
        name_lower = device_name.lower()
        matching = [d for d in devices if name_lower in d.name.lower()]

        if matching:
            selected = matching[0]
            logger.info(
                "microphone_selected",
                name=selected.name,
                index=selected.index,
                channels=selected.channels,
                filter=device_name,
            )
            return selected

        # No match found - log available devices and raise
        available = [d.name for d in devices]
        logger.warning(
            "microphone_not_found",
            filter=device_name,
            available=available,
        )
        raise RuntimeError(
            f"No microphone matching '{device_name}' found. "
            f"Available devices: {available}"
        )

    # No filter - return first suitable device (prefer default if available)
    default_devices = [d for d in devices if d.is_default]
    selected = default_devices[0] if default_devices else devices[0]

    logger.info(
        "microphone_auto_selected",
        name=selected.name,
        index=selected.index,
        channels=selected.channels,
    )
    return selected


def set_microphone_volume(volume_percent: int = 75) -> bool:
    """Set the microphone capture volume using ALSA amixer.

    This is Linux-specific and may fail on other platforms or
    if the audio device doesn't support volume control.

    Args:
        volume_percent: Volume level (0-100).

    Returns:
        True if volume was set successfully, False otherwise.
    """
    if not 0 <= volume_percent <= 100:
        logger.warning("invalid_volume", volume=volume_percent)
        return False

    try:
        # Try to set capture volume
        cmd = ["amixer", "set", "Capture", f"{volume_percent}%", "unmute"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            logger.info("volume_set", volume=volume_percent)
            return True

        logger.warning(
            "volume_set_failed",
            returncode=result.returncode,
            stderr=result.stderr.strip(),
        )
        return False

    except FileNotFoundError:
        logger.warning("amixer_not_found", msg="amixer command not available")
        return False
    except subprocess.TimeoutExpired:
        logger.warning("amixer_timeout")
        return False
    except Exception as e:
        logger.warning("volume_set_error", error=str(e))
        return False


def get_microphone_volume() -> int | None:
    """Get the current microphone capture volume.

    Returns:
        Volume percentage (0-100) or None if unable to read.
    """
    try:
        cmd = ["amixer", "get", "Capture"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            # Parse output for percentage, e.g., "[75%]"
            import re

            match = re.search(r"\[(\d+)%\]", result.stdout)
            if match:
                return int(match.group(1))

        return None

    except Exception:
        return None
