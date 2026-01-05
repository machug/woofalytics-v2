# Woofalytics Frontend

SvelteKit-based web dashboard for real-time bark detection monitoring.

## Tech Stack

- **SvelteKit** 2.x with Svelte 5 runes
- **TypeScript** with strict mode
- **openapi-fetch** for type-safe API calls
- **Vite** for development and building

## Pages

| Route | Description |
|-------|-------------|
| `/` | Mission Control dashboard (real-time monitoring) |
| `/dogs` | Dog profile management and bark tagging |
| `/fingerprints` | Browse and filter bark fingerprints |
| `/settings` | Configuration and maintenance |

## Development

```bash
npm install
npm run dev      # Start dev server on :5173
npm run build    # Build for production
npm run check    # TypeScript/Svelte checks
npm run preview  # Preview production build
```

The dev server proxies API calls to the backend at `localhost:8000`.

## Architecture

### State Management

Uses Svelte 5 runes (`$state`, `$derived`, `$effect`) with stores for:

- `barkStore` - Real-time bark events via WebSocket
- `audioStore` - Audio level updates for VU meter
- `audioConnectionState` - WebSocket connection status

### API Client

Type-safe client using `openapi-fetch` in `src/lib/api/`:

```typescript
import { api, fetchApi } from '$lib/api/client';

const dogs = await fetchApi(() => api.GET('/api/dogs'));
```

### Components

Located in `src/lib/components/`:

- **dashboard/** - BarkGauge, WaveformVisualizer, DetectionPipeline, BarkTracker
- **dogs/** - DogCard, UntaggedBarkList, BarkModal
- **ui/** - Card, Button, Badge, Modal, Spinner

### Theme

NASA Mission Control aesthetic:
- Dark glassmorphism UI
- Cyan/amber accent colors
- JetBrains Mono for metrics
- Real-time data visualization

## Production

The frontend is built to static files and served by FastAPI. No separate Node.js server required.

```bash
npm run build    # Outputs to build/
```

The backend serves these files from the `frontend/build` directory.
