/**
 * Fingerprints store for recent bark detections
 * Fetches from server on load, updates via WebSocket
 */

import { writable, derived, type Readable } from 'svelte/store';

export interface Fingerprint {
	id: string;
	timestamp: Date;
	dog_id: string | null;
	dog_name: string | null;
	match_confidence: number | null;
	detection_probability: number;
	evidence_filename: string | null;
	doa_degrees: number | null;
	duration_ms: number | null;
	pitch_hz: number | null;
}

interface FingerprintState {
	recent: Fingerprint[];
	loading: boolean;
	error: string | null;
}

const MAX_RECENT = 5;

function createFingerprintStore() {
	const { subscribe, update, set } = writable<FingerprintState>({
		recent: [],
		loading: false,
		error: null
	});

	return {
		subscribe,
		setRecent: (fingerprints: Fingerprint[]) => {
			update((state) => ({
				...state,
				recent: fingerprints.slice(0, MAX_RECENT),
				loading: false,
				error: null
			}));
		},
		addFingerprint: (fingerprint: Fingerprint) => {
			update((state) => ({
				...state,
				recent: [fingerprint, ...state.recent].slice(0, MAX_RECENT)
			}));
		},
		setLoading: (loading: boolean) => {
			update((state) => ({ ...state, loading }));
		},
		setError: (error: string | null) => {
			update((state) => ({ ...state, error, loading: false }));
		},
		reset: () =>
			set({
				recent: [],
				loading: false,
				error: null
			})
	};
}

export const fingerprintStore = createFingerprintStore();

// Derived stores
export const recentFingerprints: Readable<Fingerprint[]> = derived(
	fingerprintStore,
	($state) => $state.recent
);

export const fingerprintsLoading: Readable<boolean> = derived(
	fingerprintStore,
	($state) => $state.loading
);

/**
 * Fetch recent fingerprints from the server
 * Called on page load to persist detections across refreshes
 */
export async function fetchRecentFingerprints(limit = 5): Promise<void> {
	fingerprintStore.setLoading(true);
	try {
		const response = await fetch(`/api/fingerprints?limit=${limit}`);
		if (response.ok) {
			const data = await response.json();
			const fingerprints: Fingerprint[] = (data.items ?? []).map((item: any) => ({
				id: item.id,
				timestamp: new Date(item.timestamp),
				dog_id: item.dog_id,
				dog_name: item.dog_name,
				match_confidence: item.match_confidence,
				detection_probability: item.detection_probability ?? 0,
				evidence_filename: item.evidence_filename,
				doa_degrees: item.doa_degrees,
				duration_ms: item.duration_ms,
				pitch_hz: item.pitch_hz
			}));
			fingerprintStore.setRecent(fingerprints);
		} else {
			fingerprintStore.setError('Failed to fetch fingerprints');
		}
	} catch (e) {
		console.error('[FingerprintStore] Failed to fetch:', e);
		fingerprintStore.setError('Network error');
	}
}
