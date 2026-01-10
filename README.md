# 🐕 Woofalytics v2.4.0

**AI-powered dog bark detection and cataloging for Raspberry Pi**

A complete modernization of the original woofalytics project, built for cataloging and fingerprinting barking dogs within earshot. Uses zero-shot audio classification (CLAP) to detect barks without training data, with automatic recording for documentation purposes.

---

## Table of Contents

- [Project Goals](#project-goals)
- [Architecture Overview](#architecture-overview)
- [Detection Pipeline](#detection-pipeline)
- [File Structure](#file-structure)
- [Module Documentation](#module-documentation)
- [Configuration System](#configuration-system)
- [API Reference](#api-reference)
- [Web UI](#web-ui)
- [Hardware Requirements](#hardware-requirements)
- [Installation](#installation)
- [Docker Deployment](#docker-deployment)
- [Development](#development)
- [Testing](#testing)
- [Design Decisions](#design-decisions)
- [Known Issues & TODOs](#known-issues--todos)
- [Original Project](#original-project)
- [Versioning](#versioning)

---

## Project Goals

This project was created with specific intentions:

1. **Learning** - Push modern Python patterns to the limits (deliberately over-engineered)
2. **Dog Cataloging** - Document and fingerprint all barking dogs within earshot
3. **Hardware Optimization** - Maximize Raspberry Pi 4B capabilities
4. **Best Practices** - Latest patterns, proper architecture, comprehensive documentation

### Key Features

- **Zero-Shot Bark Detection** - CLAP-powered classification without training data (~500ms inference)
- **Multi-Layer Veto System** - Rejects speech, percussion, and bird sounds to reduce false positives
- **Direction of Arrival (DOA)** - Know which direction barks come from using stereo microphones
- **Evidence Recording** - Automatic 30-second clips with JSON metadata sidecars
- **Modern Web UI** - Real-time dashboard with WebSocket updates
- **Accessible by Design** - WCAG AA compliant, screen reader support, respects motion preferences
- **REST API** - Full OpenAPI documentation at `/api/docs`
- **Docker Support** - Easy deployment with Docker Compose
- **Flexible Configuration** - YAML config with environment variable overrides
- **Legacy MLP Support** - Optional TorchScript models for faster inference on constrained hardware

---

## Architecture Overview

```
┌───────────────────────────────────────────────────────────────┐
│                      FastAPI Application                      │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────────┐   │
│  │  REST API  │  │  WebSocket │  │     Static Files       │   │
│  │  /api/*    │  │  /ws/bark  │  │     /static/*          │   │
│  │            │  │  /ws/audio │  │                        │   │
│  └─────┬──────┘  └─────┬──────┘  └────────────────────────┘   │
│        │               │                                      │
│        └───────┬───────┘                                      │
│                ▼                                              │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                     BarkDetector                        │  │
│  │  - Coordinates audio capture, inference, callbacks      │  │
│  │  - Runs inference loop every 500ms (CLAP) or 80ms (MLP) │  │
│  │  - Produces BarkEvent objects                           │  │
│  └─────────────────────────────────────────────────────────┘  │
│        │                │                   │                 │
│        ▼                ▼                   ▼                 │
│  ┌───────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Audio     │  │  VAD Gate   │  │     DOA Estimator       │  │
│  │ Capture   │  │ (fast skip) │  │  (Bartlett/Capon/MEM)   │  │
│  └───────────┘  └──────┬──────┘  └─────────────────────────┘  │
│                        ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                    CLAP Detector                        │  │
│  │  - Zero-shot audio classification (laion/clap-htsat)    │  │
│  │  - Multi-label veto (speech, percussion, birds)         │  │
│  │  - Rolling window + high-confidence bypass              │  │ 
│  └─────────────────────────────────────────────────────────┘  │
│        │                                                      │
│        ▼                                                      │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                   EvidenceStorage                       │  │
│  │  - Records WAV clips on bark detection                  │  │
│  │  - Creates JSON metadata sidecars                       │  │
│  │  - Maintains evidence index                             │  │
│  └─────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Audio Capture** (`audio/capture.py`) runs in a background thread, filling a ring buffer
2. **BarkDetector** (`detection/model.py`) reads ~100 frames (1 second) from buffer every 500ms
3. **VAD Gate** (`detection/vad.py`) fast-rejects silent audio before expensive CLAP inference
4. **CLAP Detector** (`detection/clap.py`) runs zero-shot classification with multi-label veto:
   - Compares "dog barking" against speech, percussion, bird, and other sound labels
   - Uses rolling window (2/3 positives required) to smooth detections
   - High-confidence barks (≥80%) bypass rolling window for instant detection
   - Detection cooldown prevents rapid-fire triggers from the same sound
5. **DOA Estimator** (`detection/doa.py`) calculates direction using pyargus algorithms
6. **BarkEvent** is created and broadcast to all registered callbacks
7. **EvidenceStorage** (`evidence/storage.py`) records clips when barks are detected
8. **WebSocket** broadcasts events to connected web clients in real-time

*Note: Legacy MLP mode uses 80ms inference with TorchScript for faster but less accurate detection.*

---

## Detection Pipeline

Woofalytics uses a multi-stage filtering approach to balance accuracy with performance:

```
Audio Input → VAD Gate → YAMNet Gate → CLAP Detector → Bark Event
                ↓            ↓              ↓
             (skip)       (skip)        (detect)
```

### 1. VAD Gate (Voice Activity Detection)
- **Purpose**: Fast energy-based rejection of silent audio
- **Method**: RMS energy threshold in dB
- **Skip Rate**: ~60-80% of frames (environment dependent)
- **Latency**: <1ms

### 2. YAMNet Gate (Pre-filter)
- **Purpose**: Skip CLAP inference for non-dog sounds
- **Model**: Google's YAMNet (TensorFlow, ~3.7M params)
- **Classes**: AudioSet class 69 (Dog) and 70 (Bark)
- **Threshold**: 0.05 (kept low to avoid missing barks)
- **Skip Rate**: 30-40% of VAD-passed frames
- **Latency**: ~50ms

### 3. CLAP Detector (Primary)
- **Purpose**: Zero-shot audio classification with multi-label veto
- **Model**: LAION CLAP (`laion/clap-htsat-unfused`)
- **Features**:
  - Compares bark labels against speech, percussion, birds
  - Rolling window (2/3 positives required)
  - High-confidence bypass (≥80%)
  - Detection cooldown prevents rapid-fire
- **Latency**: ~500ms

Monitor pipeline status in real-time via the Dashboard's **Detection Pipeline** card.

---

## File Structure

```
woofalytics-v2/
├── src/woofalytics/             # Python backend
│   ├── __init__.py              # Package version and exports
│   ├── __main__.py              # CLI entry point (python -m woofalytics)
│   ├── app.py                   # FastAPI application with lifespan
│   ├── config.py                # Pydantic v2 settings system
│   │
│   ├── audio/
│   │   ├── __init__.py          # Module exports
│   │   ├── devices.py           # Microphone discovery (PyAudio wrapper)
│   │   └── capture.py           # Async audio capture with ring buffer
│   │
│   ├── detection/
│   │   ├── __init__.py          # Module exports
│   │   ├── model.py             # BarkDetector orchestrator + BarkEvent
│   │   ├── clap.py              # CLAP zero-shot classifier (primary)
│   │   ├── vad.py               # Voice activity detection gate
│   │   ├── features.py          # Mel filterbank feature extraction (legacy)
│   │   └── doa.py               # Direction of arrival estimation
│   │
│   ├── evidence/
│   │   ├── __init__.py          # Module exports
│   │   ├── storage.py           # Evidence recording and management
│   │   └── metadata.py          # JSON metadata models
│   │
│   ├── fingerprint/             # Dog identification system
│   │   ├── __init__.py
│   │   ├── storage.py           # SQLite fingerprint database
│   │   └── matcher.py           # CLAP embedding matching
│   │
│   └── api/
│       ├── __init__.py          # Module exports
│       ├── routes.py            # REST API endpoints
│       ├── schemas.py           # Pydantic response models
│       └── websocket.py         # WebSocket endpoints + ConnectionManager
│
├── frontend/                    # SvelteKit frontend (NASA Mission Control theme)
│   ├── src/
│   │   ├── routes/              # SvelteKit pages
│   │   │   ├── +page.svelte     # Dashboard with real-time monitoring
│   │   │   ├── dogs/            # Dog management page
│   │   │   ├── fingerprints/    # Fingerprints explorer
│   │   │   └── settings/        # Settings & maintenance
│   │   ├── lib/
│   │   │   ├── api/             # Type-safe API client (openapi-fetch)
│   │   │   ├── components/      # Reusable UI components
│   │   │   └── stores/          # Svelte stores for WebSocket state
│   │   └── app.css              # Global styles (glassmorphism theme)
│   ├── build/                   # Production build (gitignored)
│   ├── package.json
│   └── svelte.config.js
│
├── static/                      # Evidence audio files (served at /static)
│
├── models/
│   └── traced_model.pt          # TorchScript bark detection model
│
├── evidence/                    # Evidence recordings (created at runtime)
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Pytest fixtures
│   ├── test_config.py           # Configuration tests
│   ├── test_audio.py            # Audio module tests
│   ├── test_detection.py        # Detection module tests
│   └── test_evidence.py         # Evidence module tests
│
├── pyproject.toml               # Python packaging (PEP 517/518)
├── Dockerfile                   # Multi-stage Docker build
├── docker-compose.yml           # Docker Compose for RPi
├── config.yaml                  # Default configuration
├── .env.example                 # Environment variable template
└── README.md                    # This file
```

---

## Module Documentation

### `config.py` - Configuration System

**Pattern**: Pydantic v2 with proper nesting (BaseModel for nested, BaseSettings for root only)

```python
# Nested configs use BaseModel (NOT BaseSettings)
class AudioConfig(BaseModel):
    device_name: str | None = None
    sample_rate: int = 44100
    channels: int = 2
    # ...

# Only root uses BaseSettings
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WOOFALYTICS__",
        env_nested_delimiter="__",
    )
    audio: AudioConfig = Field(default_factory=AudioConfig)
    # ...
```

**Environment Variables**:
- Prefix: `WOOFALYTICS__`
- Nested delimiter: `__`
- Example: `WOOFALYTICS__AUDIO__SAMPLE_RATE=48000`

### `audio/devices.py` - Microphone Discovery

- `MicrophoneInfo` - Dataclass for device info
- `list_microphones(min_channels)` - List all input devices
- `find_microphone(device_name, min_channels)` - Auto-detect or filter by name
- `set_microphone_volume(percent)` - ALSA amixer wrapper (Linux only)

### `audio/capture.py` - Async Audio Capture

- `AudioFrame` - Single frame with timestamp, raw bytes, metadata
- `AsyncAudioCapture` - Runs PyAudio in background thread, async interface
  - Ring buffer (default 30 seconds)
  - `get_recent_frames(count)` - Get N most recent frames
  - `get_buffer_as_array(seconds)` - Get audio as numpy array

### `detection/features.py` - Feature Extraction

- `FeatureExtractor` - Converts audio to Mel filterbank features
  - Resamples from source rate (44.1kHz) to model rate (16kHz)
  - 80 Mel bins, 25ms frame, 10ms hop
  - Uses `torchaudio.compliance.kaldi.fbank` for Kaldi compatibility
  - Output: `(1, 480)` tensor (6 frames × 80 mels)

### `detection/doa.py` - Direction of Arrival

- `DirectionEstimator` - Estimates sound direction using ULA geometry
  - **Bartlett** - Simple beamforming (default)
  - **Capon (MVDR)** - Higher resolution
  - **MEM** - Maximum entropy, best for close sources
- `angle_to_direction(angle)` - Converts degrees to "left", "front", "right", etc.

### `detection/clap.py` - CLAP Zero-Shot Classifier (Primary)

- `CLAPConfig` - Configuration for CLAP detection
  - `bark_labels` - Positive bark sound labels
  - `speech_labels` - Human speech for veto
  - `percussive_labels` - Claps, knocks for veto
  - `bird_labels` - Bird sounds for veto
  - `threshold`, `speech_veto_threshold`, `bird_veto_threshold`
  - `rolling_window_size`, `detection_cooldown_frames`
- `CLAPDetector` - Zero-shot audio classifier using LAION CLAP
  - Uses `laion/clap-htsat-unfused` model by default
  - Caches text embeddings for efficiency
  - Multi-label detection with veto system
  - Rolling window smoothing with high-confidence bypass
  - Detection cooldown to prevent rapid-fire triggers

### `detection/vad.py` - Voice Activity Detection Gate

- `VADConfig` - Configuration for VAD gate
- `VADGate` - Fast energy-based rejection of silent audio
  - Skips expensive CLAP inference on silent frames
  - Configurable energy threshold in dB

### `detection/model.py` - Bark Detector Orchestrator

- `BarkEvent` - Detection event with timestamp, probability, DOA
- `BarkDetector` - Main orchestrator
  - Supports both CLAP (default) and legacy MLP modes
  - CLAP mode: 500ms inference interval with 1s audio windows
  - Legacy mode: 80ms inference interval with TorchScript
  - Manages callbacks for event notification
  - Tracks statistics (uptime, total barks, VAD skips)

### `evidence/metadata.py` - Metadata Models

- `DetectionInfo` - Probability, bark count, DOA values
- `DeviceInfo` - Hostname, microphone name
- `EvidenceMetadata` - Complete metadata for a recording
- `EvidenceIndex` - Index of all evidence files

### `evidence/storage.py` - Evidence Storage

- `EvidenceStorage` - Records bark clips
  - Triggers on bark detection
  - Records past context (15s) + future context (15s)
  - Saves WAV + JSON sidecar
  - Maintains searchable index

### `api/routes.py` - REST Endpoints

See [API Reference](#api-reference) below.

### `api/websocket.py` - WebSocket Streaming

- `ConnectionManager` - Manages active WebSocket connections
- `/ws/bark` - Real-time bark events
- `/ws/audio` - Real-time audio levels (VU meter)

### `app.py` - FastAPI Application

- Uses `lifespan` context manager for startup/shutdown
- Dependency injection via `app.state`
- Mounts static files, includes routers

---

## Configuration System

### config.yaml

```yaml
audio:
  device_name: null        # null = auto-detect, or "ReSpeaker"
  sample_rate: 44100       # Hz
  channels: 2              # Minimum 2 for DOA
  chunk_size: 441          # Samples per chunk (~10ms at 44.1kHz)
  volume_percent: 75       # Microphone gain (0-100)

model:
  use_clap: true           # Use CLAP zero-shot (recommended)
  clap_model: laion/clap-htsat-unfused
  clap_threshold: 0.5      # Bark confidence threshold
  clap_device: cpu         # or cuda
  vad_enabled: true        # Fast rejection of silent audio
  vad_threshold_db: -40    # Energy threshold for VAD
  # Legacy MLP settings (when use_clap: false)
  path: ./models/traced_model.pt
  target_sample_rate: 16000
  threshold: 0.88

doa:
  enabled: true
  element_spacing: 0.1     # In wavelengths
  num_elements: 2
  angle_min: 0
  angle_max: 180

evidence:
  directory: ./evidence
  past_context_seconds: 15
  future_context_seconds: 15
  include_metadata: true

webhook:
  enabled: false
  ifttt_event: woof
  # ifttt_key: set via environment

server:
  host: 0.0.0.0
  port: 8000
  enable_websocket: true

log_level: INFO            # DEBUG, INFO, WARNING, ERROR
log_format: console        # console or json
```

### Environment Variables

```bash
# Override any config value
WOOFALYTICS__LOG_LEVEL=DEBUG
WOOFALYTICS__MODEL__THRESHOLD=0.90
WOOFALYTICS__AUDIO__DEVICE_NAME=ReSpeaker
WOOFALYTICS__WEBHOOK__IFTTT_KEY=your_secret_key
```

---

## API Reference

### Health & Status

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check with uptime, bark count, evidence count |
| `/api/status` | GET | Detector status (running, uptime, last event) |
| `/api/config` | GET | Current configuration (sanitized, no secrets) |

### Bark Detection

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/bark` | GET | Latest bark event |
| `/api/bark/probability` | GET | Just the probability value |
| `/api/bark/recent?count=10` | GET | Recent events (1-100) |
| `/api/direction` | GET | Current DOA with all methods |

### Evidence

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/evidence?count=20` | GET | List recent evidence |
| `/api/evidence/stats` | GET | Storage statistics |
| `/api/evidence/{filename}` | GET | Download WAV or JSON file |
| `/api/evidence/date/{YYYY-MM-DD}` | GET | Evidence by date |

### WebSocket

| Endpoint | Description |
|----------|-------------|
| `/ws/bark` | Real-time bark events (JSON) |
| `/ws/audio` | Audio level updates at 10Hz |

### OpenAPI Documentation

- Swagger UI: `/api/docs`
- ReDoc: `/api/redoc`
- OpenAPI JSON: `/api/openapi.json`

---

## Web UI

The frontend is a **SvelteKit SPA** with a NASA Mission Control-inspired theme (glassmorphism, dark UI, cyan/amber accents).

### Pages

| Route | Description |
|-------|-------------|
| `/` | **Dashboard** - Real-time bark probability, DOA compass, VU meter, statistics |
| `/dogs` | **Dog Management** - View registered dogs, bark counts, manage profiles |
| `/fingerprints` | **Fingerprints Explorer** - Browse bark fingerprints with filtering and playback |
| `/settings` | **Settings & Maintenance** - Configuration display, data purge operations |

### Features

- **Real-time Updates** - WebSocket streams for live bark events and audio levels
- **Type-safe API Client** - Generated from OpenAPI schema using `openapi-fetch`
- **Svelte 5 Runes** - Modern reactive state with `$state`, `$derived`, `$effect`
- **Responsive Design** - Works on desktop and tablet
- **Evidence Playback** - Listen to recorded bark clips directly in the browser
- **Toast Notifications** - Non-blocking feedback replacing browser alerts
- **Active Navigation** - Clear indication of current page with amber highlight
- **Accessibility** - WCAG AA text contrast, labeled form inputs, `prefers-reduced-motion` support

### Production Serving

The SvelteKit frontend is built to static files and served directly by FastAPI. No separate Node.js server required in production.

---

## Hardware Requirements

### Minimum

- **Raspberry Pi 4 Model B** (2GB+ RAM)
- **Any USB microphone** (1+ channels)

### Recommended for DOA

- **ReSpeaker 2-Mic HAT** (~$12) - HAT form factor, 2 mics
- **ReSpeaker 4-Mic Array** (~$35) - 360° coverage

### ReSpeaker HAT Setup

```bash
# Install seeed-voicecard driver
git clone https://github.com/respeaker/seeed-voicecard
cd seeed-voicecard
sudo ./install.sh
sudo reboot
```

---

## Installation

### Quick Start (Docker)

```bash
git clone https://github.com/your-user/woofalytics.git
cd woofalytics-v2
cp .env.example .env
docker-compose up -d
```

### Manual Installation

```bash
# System dependencies (Debian/Ubuntu/Raspberry Pi OS)
sudo apt-get update
sudo apt-get install -y \
    python3.11 python3.11-venv \
    portaudio19-dev libasound2-dev \
    alsa-utils nodejs npm

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install Python package
pip install -e .

# Build frontend
cd frontend
npm install
npm run build
cd ..

# Verify audio devices
woofalytics --list-devices

# Run
woofalytics
```

### CLI Options

```
woofalytics [OPTIONS]

Options:
  -c, --config PATH       Config file (default: config.yaml)
  --host TEXT             Override host
  -p, --port INTEGER      Override port
  --reload                Enable hot reload (dev)
  --log-level LEVEL       Override log level
  --list-devices          List audio devices and exit
  --version               Show version
```

---

## Docker Deployment

### Dockerfile Features

- Multi-stage build (builder + runtime)
- Non-root user (`woofalytics`)
- Audio libraries pre-installed
- Health check included
- Evidence volume for persistence

### docker-compose.yml

```yaml
services:
  woofalytics:
    build: .
    ports:
      - "8000:8000"
    devices:
      - /dev/snd:/dev/snd    # Audio device access
    group_add:
      - audio                 # Audio group membership
    volumes:
      - ./config.yaml:/home/woofalytics/app/config.yaml:ro
      - ./evidence:/home/woofalytics/app/evidence
      - ./models:/home/woofalytics/app/models:ro
    environment:
      - TZ=Europe/London
      - WOOFALYTICS__WEBHOOK__IFTTT_KEY=${IFTTT_KEY:-}
    restart: unless-stopped
```

### Commands

```bash
# Build and start
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop
docker-compose down

# Rebuild after code changes
docker-compose up -d --build --force-recreate
```

---

## Development

### Setup

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks (optional)
pre-commit install

# Install frontend dependencies
cd frontend && npm install && cd ..
```

### Running (Backend)

```bash
# With hot reload
woofalytics --reload --log-level DEBUG

# Or directly with uvicorn
uvicorn woofalytics.app:app --reload --host 0.0.0.0 --port 8000
```

### Running (Frontend Development)

```bash
# Start the SvelteKit dev server (auto-proxies API calls to backend)
cd frontend
npm run dev

# Frontend available at http://localhost:5173
# Backend must be running on port 8000
```

### Building Frontend for Production

```bash
cd frontend
npm run build    # Outputs to frontend/build/
npm run preview  # Preview production build locally
```

### Code Quality

```bash
# Python linting
ruff check src/woofalytics

# Python type checking
mypy src/woofalytics

# Python format
ruff format src/woofalytics

# Frontend type checking
cd frontend && npm run check
```

---

## Testing

### Run Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=woofalytics --cov-report=html

# Specific module
pytest tests/test_config.py -v

# With output
pytest -s
```

### Test Structure

- `conftest.py` - Shared fixtures (mock PyAudio, test settings, etc.)
- `test_config.py` - Configuration validation
- `test_audio.py` - Audio frame and device tests
- `test_detection.py` - DOA and bark event tests
- `test_evidence.py` - Metadata and storage tests

### Mocking

Tests mock PyAudio to run without audio hardware:

```python
@pytest.fixture
def mock_pyaudio():
    with patch("pyaudio.PyAudio") as mock:
        # Configure mock device list
        yield mock
```

---

## Design Decisions

### Why Pydantic v2 with BaseModel for Nested Configs?

Using `BaseSettings` for nested configs causes environment variable conflicts. The correct pattern:
- `BaseModel` for nested configs (AudioConfig, ModelConfig, etc.)
- `BaseSettings` only for root Settings class
- Environment variables work with `__` delimiter: `WOOFALYTICS__AUDIO__SAMPLE_RATE`

### Why Async Audio Capture?

PyAudio is blocking, but FastAPI is async. Solution:
- Run PyAudio in a background daemon thread
- Use thread-safe ring buffer (deque with lock)
- Async methods for control (`start()`, `stop()`)
- Sync methods for buffer access (called from any context)

### Why Three DOA Algorithms?

Each has trade-offs:
- **Bartlett** - Robust, works well with noise
- **Capon** - Better resolution, more sensitive to calibration
- **MEM** - Best for multiple sources, computationally heavier

### Why CLAP Instead of Custom Models?

CLAP (Contrastive Language-Audio Pretraining) offers key advantages:
- **Zero-shot** - No training data required, works immediately
- **Multi-label** - Can detect bark AND check for speech/birds simultaneously
- **Veto system** - Reduces false positives by rejecting similar sounds
- **Generalizes** - Works across dog breeds without fine-tuning

The downside is slower inference (~500ms vs 80ms), which is why:
- VAD gate fast-rejects silent audio before CLAP
- High-confidence bypass (≥80%) enables instant detection
- Detection cooldown prevents rapid-fire from same sound

### Why Legacy MLP Mode?

For constrained hardware (RPi 3, RPi Zero), the legacy MLP model offers:
- 80ms inference interval (12.5 inferences/second)
- Smaller memory footprint
- Less accurate but faster

### Why JSON Sidecars for Evidence?

For documentation purposes, metadata must be:
- Human-readable (JSON, not binary)
- Separate from audio (can't be embedded in WAV easily)
- Include precise timestamps, probabilities, device info
- Machine-parseable for cataloging and fingerprinting

---

## Known Issues & TODOs

### Not Yet Implemented

1. **Event Filter** (`events/filter.py`) - Rate limiting/debouncing
2. **Webhook Notifications** - IFTTT integration
3. **Evidence Cleanup** - Automatic old file removal
4. **Audio Spectrogram** - Visual display in web UI

### Potential Improvements

1. **Prometheus Metrics** - For Grafana dashboards
2. **Home Assistant Integration** - MQTT or REST
3. **Multi-Dog Fingerprinting** - Identify individual dogs by bark signature
4. **SMS/Push Notifications** - Via Pushover/Twilio
5. **Bark Pattern Analysis** - Track frequency, duration, and timing patterns per dog

### Known Limitations

1. **Linux Only** - ALSA volume control is Linux-specific
2. **x86/ARM** - PyTorch may need ARM-specific wheels on RPi
3. **No GPU** - Inference is CPU-only (fine for RPi)

---

## Original Project

This is a fork/rewrite of the original woofalytics project. Key changes:

| Aspect | Original | v2.0 |
|--------|----------|------|
| Python | 3.9+ | 3.11+ |
| Detection | Custom MLP | CLAP zero-shot (+ legacy MLP) |
| False Positives | High | Multi-layer veto system |
| Web Framework | Basic HTTP | FastAPI |
| Config | Hardcoded | Pydantic v2 |
| Microphone | Andrea only | Any USB mic |
| Real-time | Polling | WebSocket |
| Evidence | WAV only | WAV + JSON metadata |
| Deployment | Manual | Docker |
| Tests | None | pytest suite |

---

## Versioning

Version is tracked in the `VERSION` file at the repository root. See [CHANGELOG.md](CHANGELOG.md) for release history.

---

## License

MIT License - See original project for attribution.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Run tests: `pytest`
4. Run linting: `ruff check src/`
5. Submit a pull request

---

## Quick Reference

```bash
# Start the server
woofalytics

# List audio devices
woofalytics --list-devices

# Run with debug logging
woofalytics --log-level DEBUG

# Docker
docker-compose up -d

# Run tests
pytest

# Check API docs
open http://localhost:8000/api/docs
```
