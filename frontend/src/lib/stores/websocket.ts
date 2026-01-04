/**
 * WebSocket connection management with auto-reconnection
 * Provides a singleton WebSocket connection that can be shared across the app
 */

import { writable, derived, type Readable } from 'svelte/store';

export type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'reconnecting';

interface WebSocketStore {
	state: Readable<ConnectionState>;
	lastMessage: Readable<MessageEvent | null>;
	send: (data: string | object) => void;
	connect: () => void;
	disconnect: () => void;
}

interface WebSocketConfig {
	url: string;
	reconnectInterval?: number;
	maxReconnectAttempts?: number;
}

export function createWebSocketStore(config: WebSocketConfig): WebSocketStore {
	const { url, reconnectInterval = 3000, maxReconnectAttempts = 10 } = config;

	let ws: WebSocket | null = null;
	let reconnectAttempts = 0;
	let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
	let intentionalClose = false;

	const stateStore = writable<ConnectionState>('disconnected');
	const messageStore = writable<MessageEvent | null>(null);

	function connect() {
		if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
			return;
		}

		intentionalClose = false;
		stateStore.set('connecting');

		try {
			// Build WebSocket URL relative to current host
			const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
			const wsUrl = `${wsProtocol}//${window.location.host}${url}`;
			ws = new WebSocket(wsUrl);

			ws.onopen = () => {
				stateStore.set('connected');
				reconnectAttempts = 0;
			};

			ws.onmessage = (event) => {
				messageStore.set(event);
			};

			ws.onclose = () => {
				stateStore.set('disconnected');
				ws = null;

				if (!intentionalClose && reconnectAttempts < maxReconnectAttempts) {
					scheduleReconnect();
				}
			};

			ws.onerror = () => {
				// Error handling - close will be called after this
				console.error('WebSocket error');
			};
		} catch (error) {
			console.error('Failed to create WebSocket:', error);
			stateStore.set('disconnected');
		}
	}

	function disconnect() {
		intentionalClose = true;
		if (reconnectTimer) {
			clearTimeout(reconnectTimer);
			reconnectTimer = null;
		}
		if (ws) {
			ws.close();
			ws = null;
		}
		stateStore.set('disconnected');
	}

	function scheduleReconnect() {
		if (reconnectTimer) return;

		reconnectAttempts++;
		stateStore.set('reconnecting');

		reconnectTimer = setTimeout(() => {
			reconnectTimer = null;
			connect();
		}, reconnectInterval);
	}

	function send(data: string | object) {
		if (ws && ws.readyState === WebSocket.OPEN) {
			const message = typeof data === 'string' ? data : JSON.stringify(data);
			ws.send(message);
		}
	}

	return {
		state: { subscribe: stateStore.subscribe },
		lastMessage: { subscribe: messageStore.subscribe },
		send,
		connect,
		disconnect
	};
}

// Singleton audio WebSocket for real-time audio levels
export const audioWebSocket = createWebSocketStore({
	url: '/ws/audio',
	reconnectInterval: 3000,
	maxReconnectAttempts: 10
});

// Connection state derived stores
export const audioConnectionState = audioWebSocket.state;
export const isAudioConnected = derived(audioConnectionState, ($state) => $state === 'connected');
