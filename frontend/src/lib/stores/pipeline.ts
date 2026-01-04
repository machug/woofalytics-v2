/**
 * Detection pipeline state store
 * Tracks real-time detection pipeline status for debugging
 */

import { writable, derived, type Readable } from 'svelte/store';

export interface VADState {
	passed: boolean;
	level_db: number;
	threshold_db: number;
}

export interface YAMNetState {
	passed: boolean;
	dog_probability: number;
	threshold: number;
}

export interface CLAPState {
	probability: number;
	is_barking: boolean;
	top_label: string;
	threshold: number;
	top_scores: Record<string, number>;
}

export interface PipelineStats {
	vad_skipped: number;
	yamnet_skipped: number;
	clap_inferences: number;
	total_barks: number;
}

export interface PipelineState {
	stage: 'vad_rejected' | 'yamnet_rejected' | 'clap_rejected' | 'bark_detected' | null;
	vad: VADState | null;
	yamnet: YAMNetState | null;
	clap: CLAPState | null;
	stats: PipelineStats | null;
	connected: boolean;
}

const initialState: PipelineState = {
	stage: null,
	vad: null,
	yamnet: null,
	clap: null,
	stats: null,
	connected: false
};

function createPipelineStore() {
	const { subscribe, update, set } = writable<PipelineState>(initialState);
	let ws: WebSocket | null = null;
	let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

	function connect() {
		if (ws?.readyState === WebSocket.OPEN) return;

		const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
		const host = window.location.hostname;
		const port = '8000'; // Backend port
		const url = `${protocol}//${host}:${port}/ws/pipeline`;

		console.log('[PipelineStore] Connecting to', url);
		ws = new WebSocket(url);

		ws.onopen = () => {
			console.log('[PipelineStore] Connected');
			update((state) => ({ ...state, connected: true }));
		};

		ws.onmessage = (event) => {
			try {
				const data = JSON.parse(event.data);
				if (data.type === 'pipeline_state') {
					update((state) => ({
						...state,
						stage: data.data.stage || null,
						vad: data.data.vad || null,
						yamnet: data.data.yamnet || null,
						clap: data.data.clap || null,
						stats: data.data.stats || null
					}));
				}
			} catch (e) {
				console.error('[PipelineStore] Parse error:', e);
			}
		};

		ws.onclose = () => {
			console.log('[PipelineStore] Disconnected');
			update((state) => ({ ...state, connected: false }));
			// Reconnect after 2 seconds
			reconnectTimer = setTimeout(connect, 2000);
		};

		ws.onerror = (error) => {
			console.error('[PipelineStore] Error:', error);
		};
	}

	function disconnect() {
		if (reconnectTimer) {
			clearTimeout(reconnectTimer);
			reconnectTimer = null;
		}
		if (ws) {
			ws.close();
			ws = null;
		}
		set(initialState);
	}

	return {
		subscribe,
		connect,
		disconnect,
		reset: () => set(initialState)
	};
}

export const pipelineStore = createPipelineStore();

// Derived stores for specific data
export const pipelineStage: Readable<string | null> = derived(
	pipelineStore,
	($state) => $state.stage
);

export const vadState: Readable<VADState | null> = derived(pipelineStore, ($state) => $state.vad);

export const yamnetState: Readable<YAMNetState | null> = derived(
	pipelineStore,
	($state) => $state.yamnet
);

export const clapState: Readable<CLAPState | null> = derived(
	pipelineStore,
	($state) => $state.clap
);

export const pipelineStats: Readable<PipelineStats | null> = derived(
	pipelineStore,
	($state) => $state.stats
);

export const pipelineConnected: Readable<boolean> = derived(
	pipelineStore,
	($state) => $state.connected
);
