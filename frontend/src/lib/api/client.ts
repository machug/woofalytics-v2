import createClient from 'openapi-fetch';
import type { paths } from './types';

// Create typed API client
export const api = createClient<paths>({
	baseUrl: ''
});

// Helper for common patterns
export async function fetchApi<T>(
	fetcher: () => Promise<{ data?: T; error?: unknown }>
): Promise<T> {
	const { data, error } = await fetcher();
	if (error) {
		throw new Error(typeof error === 'string' ? error : JSON.stringify(error));
	}
	if (data === undefined) {
		throw new Error('No data returned from API');
	}
	return data;
}

// Re-export types for convenience
export type { paths };
