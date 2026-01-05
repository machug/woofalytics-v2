# Changelog

All notable changes to Woofalytics will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2.1.0] - 2026-01-05

### Added
- MET (Mission Elapsed Time) clock in header showing detector uptime
- Acoustic tie-breaking for fingerprint matching when CLAP margin is low
- Gate statistics exposed via `/api/status` endpoint

### Fixed
- Evidence recording no longer blocks the event loop (callbacks run in executor)
- Fingerprint-to-evidence linking runs asynchronously

## [2.0.0] - 2026-01-05

### Added
- YAMNet pre-filter for two-stage bark detection (30-40% inference skip rate)
- Real-time detection pipeline monitor in dashboard
- Bulk tagging for untagged barks
- Bark tracker component replacing particle visualization
- Dog confirmation workflow with UI controls

### Changed
- Waveform colors now use hysteresis to prevent flickering
- Frontend migrated to Svelte 5 with runes ($state, $derived)
- API field names aligned (confirmed, total_barks)

### Fixed
- YAMNet forced to CPU to avoid CUDA/XLA JIT errors
- Dog confirmation endpoint now accepts request body
- Bark count display on dog cards

## [0.1.0] - 2025-12-01

### Added
- CLAP-based zero-shot bark detection
- Multi-stage filtering: VAD → YAMNet → CLAP
- Evidence recording with 30-second context windows
- Dog profile management with fingerprinting
- SvelteKit frontend with NASA Mission Control theme
- WebSocket real-time updates
- Docker deployment support
