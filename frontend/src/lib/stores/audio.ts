/**
 * Audio level state store
 * Tracks real-time audio levels from the WebSocket
 */

import { writable, derived, type Readable } from 'svelte/store';
import { audioWebSocket } from './websocket';

interface AudioState {
	level: number; // 0-1 normalized audio level
	peak: number; // Recent peak level for visual feedback
	isClipping: boolean;
	history: number[]; // Recent levels for waveform visualization
}

const HISTORY_SIZE = 128; // Number of samples to keep for waveform

function createAudioStore() {
	const { subscribe, update, set } = writable<AudioState>({
		level: 0,
		peak: 0,
		isClipping: false,
		history: new Array(HISTORY_SIZE).fill(0)
	});

	let peakDecayTimer: ReturnType<typeof setTimeout> | null = null;

	// Smoothing factor: higher = more smoothing (0.7 = 70% old value, 30% new)
	const SMOOTHING = 0.7;

	return {
		subscribe,
		setLevel: (level: number) => {
			update((state) => {
				const clampedLevel = Math.max(0, Math.min(1, level));

				// Apply exponential smoothing to reduce flicker
				const smoothedLevel = state.level * SMOOTHING + clampedLevel * (1 - SMOOTHING);

				const newPeak = clampedLevel > state.peak ? clampedLevel : state.peak;
				const isClipping = smoothedLevel > 0.95;

				// Add smoothed value to history, remove oldest
				const newHistory = [...state.history.slice(1), smoothedLevel];

				return {
					level: clampedLevel,
					peak: newPeak,
					isClipping,
					history: newHistory
				};
			});

			// Decay peak over time
			if (peakDecayTimer) clearTimeout(peakDecayTimer);
			peakDecayTimer = setTimeout(() => {
				update((state) => ({
					...state,
					peak: Math.max(state.level, state.peak * 0.95)
				}));
			}, 100);
		},
		reset: () =>
			set({
				level: 0,
				peak: 0,
				isClipping: false,
				history: new Array(HISTORY_SIZE).fill(0)
			})
	};
}

export const audioStore = createAudioStore();

// Derived stores
export const audioLevel: Readable<number> = derived(audioStore, ($state) => $state.level);

export const audioPeak: Readable<number> = derived(audioStore, ($state) => $state.peak);

export const isClipping: Readable<boolean> = derived(audioStore, ($state) => $state.isClipping);

export const audioHistory: Readable<number[]> = derived(audioStore, ($state) => $state.history);

// Process incoming WebSocket messages for audio levels
let messageUnsubscribe: (() => void) | null = null;

export function startAudioListener() {
	if (messageUnsubscribe) return;

	messageUnsubscribe = audioWebSocket.lastMessage.subscribe((event) => {
		if (!event) return;

		try {
			const data = JSON.parse(event.data);

			if (data.type === 'audio_level') {
				// Backend sends {type: "audio_level", data: {level, peak}}
				audioStore.setLevel(data.data?.level || 0);
			}
		} catch {
			// Ignore non-JSON messages or parsing errors
		}
	});

	// Connect the WebSocket
	audioWebSocket.connect();
}

export function stopAudioListener() {
	if (messageUnsubscribe) {
		messageUnsubscribe();
		messageUnsubscribe = null;
	}
	audioStore.reset();
}
