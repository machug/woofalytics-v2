# feat: Migrate Woofalytics Frontend to SvelteKit

## Overview

Migrate Woofalytics from vanilla HTML/CSS/JS with inline scripts to a modern SvelteKit application with TypeScript. The Python/FastAPI backend remains unchanged - this migration focuses exclusively on the presentation layer.

**Current State:**
- 4 static HTML pages with ~5000 lines of inline JavaScript
- ES6 classes for state management (DogsAdmin, FingerprintsExplorer, etc.)
- Shared CSS variables in `styles.css` (~1750 lines)
- Real-time WebSocket connections for bark detection and audio levels
- Canvas-based visualizations (waveform, particle effects)
- Chart.js for data visualization

**Target State:**
- SvelteKit SPA with TypeScript
- Component-based architecture with reactive stores
- Auto-generated API types from FastAPI OpenAPI schema
- Proper WebSocket lifecycle management
- Preserved NASA mission control aesthetic

## Technical Approach

### Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Rendering** | SPA mode (`ssr: false`) | Dashboard is real-time, no SEO needed |
| **Adapter** | `adapter-static` | FastAPI serves built output from `/static` |
| **TypeScript** | Yes, strict mode | Type safety for API contracts |
| **State** | Svelte 5 runes + stores | Modern reactivity, WebSocket state sharing |
| **Styling** | Keep custom CSS | Preserve NASA theme, migrate to scoped styles |
| **API Types** | Auto-generate from OpenAPI | Prevent type drift, single source of truth |

### Directory Structure

```
frontend/                          # New SvelteKit project
├── src/
│   ├── lib/
│   │   ├── api/
│   │   │   ├── client.ts         # Fetch wrapper with error handling
│   │   │   └── types.ts          # Auto-generated from OpenAPI
│   │   ├── components/
│   │   │   ├── ui/               # Generic components
│   │   │   │   ├── Button.svelte
│   │   │   │   ├── Modal.svelte
│   │   │   │   ├── Badge.svelte
│   │   │   │   └── Card.svelte
│   │   │   ├── dashboard/        # Dashboard-specific
│   │   │   │   ├── BarkGauge.svelte
│   │   │   │   ├── WaveformVisualizer.svelte
│   │   │   │   ├── ParticleSystem.svelte
│   │   │   │   └── TelemetryStrip.svelte
│   │   │   ├── dogs/             # Dog management
│   │   │   │   ├── DogCard.svelte
│   │   │   │   ├── DogForm.svelte
│   │   │   │   ├── BarkModal.svelte
│   │   │   │   └── UntaggedBarkList.svelte
│   │   │   └── fingerprints/     # Fingerprint explorer
│   │   │       ├── FingerprintTable.svelte
│   │   │       ├── FilterPanel.svelte
│   │   │       ├── StatsChart.svelte
│   │   │       └── AudioPlayer.svelte
│   │   ├── stores/
│   │   │   ├── websocket.ts      # WebSocket connection management
│   │   │   ├── bark.ts           # Real-time bark state
│   │   │   ├── audio.ts          # Audio level state
│   │   │   └── dogs.ts           # Dog list cache
│   │   └── utils/
│   │       ├── format.ts         # Date, number formatting
│   │       └── audio.ts          # Audio playback utilities
│   ├── routes/
│   │   ├── +layout.svelte        # Root layout with nav
│   │   ├── +layout.ts            # SPA mode config
│   │   ├── +page.svelte          # Dashboard (/)
│   │   ├── dogs/
│   │   │   └── +page.svelte      # Dog management
│   │   ├── fingerprints/
│   │   │   └── +page.svelte      # Fingerprint explorer
│   │   └── settings/
│   │       └── +page.svelte      # Maintenance
│   └── app.css                   # Global styles (NASA theme)
├── static/                        # Static assets
├── vite.config.ts                # API proxy config
├── svelte.config.js
└── package.json
```

### WebSocket Architecture

```typescript
// src/lib/stores/websocket.ts
import { writable, derived } from 'svelte/store';

interface WebSocketState {
  barkSocket: WebSocket | null;
  audioSocket: WebSocket | null;
  connected: boolean;
  reconnecting: boolean;
  error: string | null;
}

function createWebSocketStore() {
  const { subscribe, set, update } = writable<WebSocketState>({
    barkSocket: null,
    audioSocket: null,
    connected: false,
    reconnecting: false,
    error: null
  });

  let reconnectAttempts = 0;
  const MAX_RECONNECT_ATTEMPTS = 5;
  const RECONNECT_DELAY = 3000;

  return {
    subscribe,
    connect: () => { /* ... */ },
    disconnect: () => { /* ... */ },
    // Reconnection with exponential backoff
  };
}
```

### API Client Pattern

```typescript
// src/lib/api/client.ts
import type { paths } from './types';
import createClient from 'openapi-fetch';

export const api = createClient<paths>({
  baseUrl: import.meta.env.DEV ? '' : '/api'
});

// Usage:
const { data, error } = await api.GET('/api/dogs');
```

## Implementation Phases

### Phase 1: Foundation
**Goal:** SvelteKit project setup, build pipeline, API type generation

**Tasks:**
- [ ] Initialize SvelteKit project with TypeScript
  - `frontend/package.json`
  - `frontend/svelte.config.js`
  - `frontend/tsconfig.json`
- [ ] Configure Vite proxy for development
  - `frontend/vite.config.ts` - proxy `/api` and `/ws` to FastAPI
- [ ] Set up OpenAPI type generation
  - Install `openapi-typescript`
  - Add npm script: `"types": "openapi-typescript http://localhost:8000/openapi.json -o src/lib/api/types.ts"`
  - `frontend/src/lib/api/types.ts` (generated)
- [ ] Create API client wrapper
  - `frontend/src/lib/api/client.ts`
- [ ] Configure SPA mode
  - `frontend/src/routes/+layout.ts` with `ssr = false`
- [ ] Migrate global CSS
  - `frontend/src/app.css` - copy CSS variables and base styles
- [ ] Create root layout with navigation
  - `frontend/src/routes/+layout.svelte`

**Acceptance Criteria:**
- [ ] `npm run dev` starts SvelteKit on port 5173
- [ ] API calls proxy to FastAPI on port 8000
- [ ] TypeScript types generated from OpenAPI schema
- [ ] Navigation between routes works

### Phase 2: Settings Page (Simplest)
**Goal:** Migrate settings/maintenance page as proof of concept

**Tasks:**
- [ ] Create settings page structure
  - `frontend/src/routes/settings/+page.svelte`
- [ ] Build reusable UI components
  - `frontend/src/lib/components/ui/Button.svelte`
  - `frontend/src/lib/components/ui/Card.svelte`
  - `frontend/src/lib/components/ui/Modal.svelte`
  - `frontend/src/lib/components/ui/Badge.svelte`
- [ ] Implement statistics display
  - Fetch `/api/fingerprints/stats` and `/api/evidence/stats`
  - Display in styled cards
- [ ] Implement purge operations
  - Confirmation modal with danger styling
  - POST to maintenance endpoints
  - Success/error toast notifications
- [ ] Implement recalculate bark counts
  - POST `/api/maintenance/recalculate-bark-counts`
  - Loading state, result display

**Acceptance Criteria:**
- [ ] Statistics load and display correctly
- [ ] Purge operations work with confirmation
- [ ] Error states handled gracefully
- [ ] Visual parity with current page

### Phase 3: Dog Management (CRUD)
**Goal:** Full dog management with modals and tagging

**Tasks:**
- [ ] Create dogs page structure
  - `frontend/src/routes/dogs/+page.svelte`
- [ ] Build dog-specific components
  - `frontend/src/lib/components/dogs/DogCard.svelte`
  - `frontend/src/lib/components/dogs/DogForm.svelte`
  - `frontend/src/lib/components/dogs/BarkModal.svelte`
  - `frontend/src/lib/components/dogs/UntaggedBarkList.svelte`
- [ ] Implement dog CRUD operations
  - GET `/api/dogs` - list with stats
  - POST `/api/dogs` - create
  - PUT `/api/dogs/{id}` - update
  - DELETE `/api/dogs/{id}` - delete with confirmation
- [ ] Implement confirmation workflow
  - POST `/api/dogs/{id}/confirm`
  - POST `/api/dogs/{id}/unconfirm`
- [ ] Implement bark viewing modal
  - GET `/api/dogs/{id}/barks`
  - Audio playback with `/api/evidence/{filename}?format=opus`
- [ ] Implement untagged bark tagging
  - GET `/api/barks/untagged`
  - POST `/api/barks/{id}/tag`
  - Bulk tagging support
- [ ] Create dogs store for caching
  - `frontend/src/lib/stores/dogs.ts`

**Acceptance Criteria:**
- [ ] All CRUD operations work correctly
- [ ] Confirmation workflow toggles correctly
- [ ] Bark modal shows barks with audio playback
- [ ] Untagged barks can be tagged to dogs
- [ ] Optimistic updates for better UX

### Phase 4: Fingerprints Explorer (Complex Data)
**Goal:** Filtering, pagination, Chart.js visualization

**Tasks:**
- [ ] Create fingerprints page structure
  - `frontend/src/routes/fingerprints/+page.svelte`
- [ ] Build fingerprint components
  - `frontend/src/lib/components/fingerprints/FingerprintTable.svelte`
  - `frontend/src/lib/components/fingerprints/FilterPanel.svelte`
  - `frontend/src/lib/components/fingerprints/StatsChart.svelte`
  - `frontend/src/lib/components/fingerprints/AudioPlayer.svelte`
- [ ] Implement filtering system
  - Dog filter dropdown
  - Date range picker
  - Tagged/untagged toggle
  - Confidence threshold slider
- [ ] Implement pagination
  - Offset-based pagination (20 per page)
  - Page navigation controls
  - URL query param sync (`?page=2&dog_id=xxx`)
- [ ] Implement Chart.js visualization
  - Dynamic import for code splitting
  - Fingerprints over time chart
  - Per-dog distribution chart
  - Proper cleanup on filter change
- [ ] Implement audio playback
  - HTML5 Audio with Opus format
  - Play/pause controls
  - Single active player (stop others on play)

**Acceptance Criteria:**
- [ ] Filters work correctly with URL sync
- [ ] Pagination handles edge cases
- [ ] Charts update smoothly on filter change
- [ ] Audio playback works for all fingerprints
- [ ] No memory leaks on repeated filter changes

### Phase 5: Dashboard (Real-time)
**Goal:** WebSocket integration, canvas visualizations

**Tasks:**
- [ ] Create dashboard page structure
  - `frontend/src/routes/+page.svelte`
- [ ] Build dashboard components
  - `frontend/src/lib/components/dashboard/BarkGauge.svelte` (SVG)
  - `frontend/src/lib/components/dashboard/WaveformVisualizer.svelte` (Canvas)
  - `frontend/src/lib/components/dashboard/ParticleSystem.svelte` (Canvas)
  - `frontend/src/lib/components/dashboard/TelemetryStrip.svelte`
  - `frontend/src/lib/components/dashboard/DirectionCompass.svelte`
  - `frontend/src/lib/components/dashboard/RecentActivity.svelte`
- [ ] Implement WebSocket stores
  - `frontend/src/lib/stores/websocket.ts`
  - `frontend/src/lib/stores/bark.ts`
  - `frontend/src/lib/stores/audio.ts`
- [ ] Implement WebSocket lifecycle
  - Connect on mount, disconnect on destroy
  - Reconnection with exponential backoff
  - Connection status indicator
- [ ] Port waveform visualizer
  - Web Audio API integration
  - RequestAnimationFrame loop
  - Cleanup on unmount
- [ ] Port particle system
  - Trigger on bark detection
  - Memory-efficient particle pool
  - Cleanup on unmount
- [ ] Implement real-time statistics
  - Bark counter
  - Peak probability tracking
  - Session duration

**Acceptance Criteria:**
- [ ] WebSocket connects and receives events
- [ ] Waveform visualizer updates in real-time
- [ ] Particle effects trigger on bark detection
- [ ] All gauges and indicators update correctly
- [ ] No memory leaks after 1+ hour session
- [ ] Reconnection works after network drop

### Phase 6: Integration & Polish
**Goal:** Final integration, testing, deployment

**Tasks:**
- [ ] Update FastAPI to serve SvelteKit build
  - Modify `app.py` to mount `/frontend/build` as static
  - Handle SPA routing (return index.html for unmatched routes)
- [ ] Remove legacy static files
  - Archive `static/*.html` files
  - Keep `static/app.js` until dashboard migration complete
- [ ] Cross-browser testing
  - Chrome, Firefox, Safari
  - Mobile responsiveness
- [ ] Performance optimization
  - Bundle size analysis
  - Lazy loading for Chart.js
  - Image optimization
- [ ] Long session testing
  - 1-hour dashboard session
  - Memory profiling
  - WebSocket stability
- [ ] Update documentation
  - README with new frontend setup
  - Development workflow

**Acceptance Criteria:**
- [ ] Production build works with FastAPI
- [ ] All pages function correctly
- [ ] No console errors or warnings
- [ ] Memory stable over long sessions
- [ ] Bundle size under 500KB gzipped

## Risk Analysis & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| WebSocket lifecycle issues | High | High | Create dedicated store, thorough onDestroy cleanup |
| Canvas memory leaks | High | High | Implement particle pool, RAF cleanup, profiling |
| Chart.js integration | Medium | Medium | Use dynamic import, test destroy/recreate cycle |
| Type drift from backend | Medium | High | Auto-generate types, CI check for schema changes |
| CSS migration breaks theme | Medium | Medium | Side-by-side comparison, keep original as reference |
| Build integration with FastAPI | Medium | High | Test early in Phase 1, document proxy config |

## Success Metrics

1. **Feature Parity**: All existing functionality preserved
2. **Code Quality**: TypeScript strict mode, no `any` types
3. **Performance**:
   - Initial load < 3s on 3G
   - No memory growth over 1-hour session
   - WebSocket reconnect < 5s after drop
4. **Bundle Size**: < 500KB gzipped (excluding Chart.js chunk)
5. **Maintainability**: Component isolation, clear store patterns

## Dependencies & Prerequisites

- [ ] Node.js 18+ installed
- [ ] FastAPI backend running for development
- [ ] OpenAPI schema accessible at `/openapi.json`
- [ ] Current static files archived for reference

## References

### Internal
- `static/index.html` - Current dashboard implementation
- `static/dogs.html` - Current dog management (lines 965-1619 for JS)
- `static/fingerprints.html` - Current fingerprint explorer
- `static/settings.html` - Current settings page
- `static/app.js` - Waveform and particle implementations (lines 730-884)
- `static/styles.css` - CSS variables and theme (lines 3-50)
- `src/woofalytics/api/routes.py` - API endpoints
- `src/woofalytics/api/schemas.py` - Pydantic schemas

### External
- [SvelteKit Documentation](https://kit.svelte.dev/docs)
- [Svelte 5 Runes](https://svelte.dev/docs/svelte/what-are-runes)
- [openapi-typescript](https://github.com/openapi-ts/openapi-typescript)
- [SvelteKit + FastAPI Tutorial](https://turtledev.io/blog/how-to-build-sveltekit-spa-with-fastapi-backend)
- [WebSocket in SvelteKit](https://www.inngest.com/blog/building-a-realtime-websocket-app-using-sveltekit)
