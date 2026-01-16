# Changelog

All notable changes to Woofalytics will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2.5.0] - 2026-01-16

### Added
- **Bark Management from Dog Modal**: Reassign barks to different dogs, unassign to move back to untagged queue, or delete (mark as false positive) directly from the dog's bark list
- **Last Heard Indicator**: Dog profiles now show when each dog was last heard (teal audio icon) on both the Dogs page and Dashboard overview
- **Webhook Notifications**: Configurable webhook system for bark alerts with customizable payloads
- **Quiet Hours Mode**: Schedule reduced sensitivity periods (e.g., nighttime) via Settings UI
- **Clustering UI**: Visual interface for analyzing untagged barks and creating new dog profiles from clusters
- **Fingerprint Purge**: Remove orphaned fingerprints without audio evidence files
- **Persistent Dashboard Stats**: Bark counts and recent detections survive page refreshes

### Fixed
- **Accurate Last Seen Timestamps**: `last_seen` now computed from actual bark timestamps, not profile modification time
- **Relative Date Display**: Older dates now show "Xd ago" instead of absolute dates

### Changed
- Dog stats (first_seen, last_seen, total_barks) computed dynamically from fingerprints table

## [2.4.0] - 2026-01-10

### Added
- Toast notification system replacing browser alert() dialogs
- Active navigation state indicator with amber highlight
- `prefers-reduced-motion` support for users with vestibular disorders
- Accessible form labels (visually hidden where appropriate)

### Fixed
- Text contrast now meets WCAG AA compliance (--text-muted: 4.5:1 ratio)

### Accessibility
- Screen reader support: `aria-current="page"` on active nav links
- Form inputs properly labeled for assistive technology
- Animations respect OS-level motion preferences

## [2.3.0] - 2026-01-10

### Added
- Audio resampling cache to eliminate redundant sample rate conversions
- Startup warning when authentication is disabled

### Changed
- Default server binding changed from 0.0.0.0 to 127.0.0.1 (security hardening)
- Fingerprint processing now runs in thread pool (no longer blocks event loop)

### Removed
- Unused ClusterInfo class and clusters table (YAGNI cleanup)
- Unused describe_bark() and get_feature_comparison() methods
- Duplicate BarkFingerprint construction code (extracted to helper)

## [2.2.0] - 2026-01-07

### Added
- Bark confirmation workflow: confirm untagged barks as genuine (even if dog unknown)
- Min harmonic ratio setting exposed in Settings UI (tunable HPSS filter)
- Expanded rejection reasons: traffic, music, machinery, siren
- Settings UI for backend detection parameters

### Changed
- Default min harmonic ratio lowered from 0.3 to 0.1 (accepts noisier barks)

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
