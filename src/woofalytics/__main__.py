"""Woofalytics entry point.

This module provides the main entry point for running
Woofalytics as a standalone application or module.

Usage:
    python -m woofalytics
    python -m woofalytics --config config.yaml
    woofalytics  # If installed via pip
"""

# Limit ML library threads BEFORE any imports
# Prevents PyTorch/TensorFlow/OpenBLAS from spawning unlimited threads
import os
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "4")

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

from woofalytics import __version__


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Woofalytics - AI-powered dog bark detection with evidence collection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    woofalytics                          Start with default settings
    woofalytics --config config.yaml     Use custom config file
    woofalytics --host 0.0.0.0 --port 8080  Custom host/port
    woofalytics --reload                 Enable hot reload (development)
        """,
    )

    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=Path("config.yaml"),
        help="Path to configuration file (default: config.yaml)",
    )

    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host to bind to (overrides config)",
    )

    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=None,
        help="Port to bind to (overrides config)",
    )

    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable hot reload for development",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Logging level (overrides config)",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List available audio input devices and exit",
    )

    return parser.parse_args()


def list_audio_devices() -> None:
    """List available audio input devices."""
    from woofalytics.audio.devices import list_microphones

    print("\nAvailable audio input devices:\n")

    devices = list_microphones(min_channels=1)

    if not devices:
        print("  No audio input devices found.")
        return

    for device in devices:
        marker = " (default)" if device.is_default else ""
        print(f"  [{device.index}] {device.name}")
        print(f"      Channels: {device.channels}, Sample Rate: {device.sample_rate}Hz{marker}")
        print()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Handle --list-devices
    if args.list_devices:
        list_audio_devices()
        return 0

    # Load config to get defaults
    from woofalytics.config import load_settings

    config_path = args.config if args.config.exists() else None
    settings = load_settings(config_path)

    # Override with command line args
    host = args.host or settings.server.host
    port = args.port or settings.server.port
    log_level = (args.log_level or settings.log_level).lower()

    print(
        f"""
╦ ╦┌─┐┌─┐┌─┐┌─┐┬ ┬ ┬┌┬┐┬┌─┐┌─┐
║║║│ ││ │├┤ ├─┤│ └┬┘ │ ││  └─┐
╚╩╝└─┘└─┘└  ┴ ┴┴─┘┴  ┴ ┴└─┘└─┘
           v{__version__}

AI-powered dog bark detection with evidence collection
Starting server at http://{host}:{port}
"""
    )

    # Run uvicorn
    uvicorn.run(
        "woofalytics.app:app",
        host=host,
        port=port,
        reload=args.reload,
        log_level=log_level,
        access_log=log_level == "debug",
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
