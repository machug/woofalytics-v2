/**
 * Bark detection state store
 * Tracks real-time bark events, counts, and recent detections
 */

import { writable, derived, type Readable } from 'svelte/store';
import { barkWebSocket } from './websocket';

export interface BarkEvent {
	id: string;
	timestamp: Date;
	confidence: number;
	duration_ms: number;
	pitch_hz: number | null;
	dog_id: string | null;
	dog_name: string | null;
	evidence_file: string | null;
}

interface BarkState {
	recentBarks: BarkEvent[];
	totalCount: number;
	todayCount: number;
	lastBark: BarkEvent | null;
	isDetecting: boolean;
	uptimeSeconds: number;
}

const MAX_RECENT_BARKS = 50;

function createBarkStore() {
	const { subscribe, update, set } = writable<BarkState>({
		recentBarks: [],
		totalCount: 0,
		todayCount: 0,
		lastBark: null,
		isDetecting: false,
		uptimeSeconds: 0
	});

	return {
		subscribe,
		addBark: (bark: BarkEvent) => {
			update((state) => ({
				...state,
				recentBarks: [bark, ...state.recentBarks].slice(0, MAX_RECENT_BARKS),
				totalCount: state.totalCount + 1,
				todayCount: state.todayCount + 1,
				lastBark: bark
			}));
		},
		setDetecting: (detecting: boolean) => {
			update((state) => ({ ...state, isDetecting: detecting }));
		},
		setTotalCount: (count: number) => {
			update((state) => ({ ...state, totalCount: count }));
		},
		setTodayCount: (count: number) => {
			update((state) => ({ ...state, todayCount: count }));
		},
		setUptime: (seconds: number) => {
			update((state) => ({ ...state, uptimeSeconds: seconds }));
		},
		incrementUptime: () => {
			update((state) => ({ ...state, uptimeSeconds: state.uptimeSeconds + 1 }));
		},
		resetSession: () => {
			update((state) => ({
				...state,
				todayCount: 0,
				recentBarks: []
			}));
		},
		reset: () =>
			set({
				recentBarks: [],
				totalCount: 0,
				todayCount: 0,
				lastBark: null,
				isDetecting: false,
				uptimeSeconds: 0
			})
	};
}

export const barkStore = createBarkStore();

// Derived stores for specific data
export const recentBarks: Readable<BarkEvent[]> = derived(
	barkStore,
	($state) => $state.recentBarks
);

export const lastBark: Readable<BarkEvent | null> = derived(barkStore, ($state) => $state.lastBark);

export const todayBarkCount: Readable<number> = derived(
	barkStore,
	($state) => $state.todayCount
);

export const totalBarkCount: Readable<number> = derived(
	barkStore,
	($state) => $state.totalCount
);

export const isDetecting: Readable<boolean> = derived(
	barkStore,
	($state) => $state.isDetecting
);

export const uptimeSeconds: Readable<number> = derived(
	barkStore,
	($state) => $state.uptimeSeconds
);

// Process incoming WebSocket messages
let messageUnsubscribe: (() => void) | null = null;
let uptimeInterval: ReturnType<typeof setInterval> | null = null;

export function startBarkListener() {
	if (messageUnsubscribe) return;

	console.log('[BarkStore] Starting bark listener');

	messageUnsubscribe = barkWebSocket.lastMessage.subscribe((event) => {
		if (!event) return;

		try {
			const data = JSON.parse(event.data);

			// Backend sends: {type: "bark_event", data: {timestamp, probability, is_barking, doa?}}
			if (data.type === 'bark_event' && data.data?.is_barking) {
				const bark: BarkEvent = {
					id: crypto.randomUUID(),
					timestamp: new Date(data.data.timestamp || Date.now()),
					confidence: data.data.probability || 0,
					duration_ms: 0,
					pitch_hz: null,
					dog_id: null,
					dog_name: null,
					evidence_file: null
				};
				barkStore.addBark(bark);
			} else if (data.type === 'status') {
				// Initial status message from backend
				barkStore.setDetecting(data.data?.running === true);
				// Set uptime from backend (persists across page reloads)
				if (typeof data.data?.uptime_seconds === 'number') {
					barkStore.setUptime(Math.floor(data.data.uptime_seconds));
				}
			}
		} catch (e) {
			console.error('[BarkStore] Parse error:', e);
		}
	});

	// Start uptime counter (increment every second)
	if (!uptimeInterval) {
		uptimeInterval = setInterval(() => {
			barkStore.incrementUptime();
		}, 1000);
	}

	// Connect the WebSocket
	console.log('[BarkStore] Connecting WebSocket');
	barkWebSocket.connect();
}

export function stopBarkListener() {
	if (messageUnsubscribe) {
		messageUnsubscribe();
		messageUnsubscribe = null;
	}
	if (uptimeInterval) {
		clearInterval(uptimeInterval);
		uptimeInterval = null;
	}
	barkWebSocket.disconnect();
}

/**
 * Fetch today's bark count from the server
 * Called on page load to persist count across refreshes
 */
export async function fetchTodayStats(): Promise<void> {
	try {
		const response = await fetch('/api/summary/daily');
		if (response.ok) {
			const data = await response.json();
			barkStore.setTodayCount(data.total_barks ?? 0);
		}
	} catch (e) {
		console.error('[BarkStore] Failed to fetch today stats:', e);
	}
}
