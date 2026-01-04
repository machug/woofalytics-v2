// This file will be auto-generated from the FastAPI OpenAPI schema
// Run: npm run types:generate
// For now, define placeholder types based on existing API structure

export interface paths {
	'/api/dogs': {
		get: {
			responses: {
				200: {
					content: {
						'application/json': Dog[];
					};
				};
			};
		};
		post: {
			requestBody: {
				content: {
					'application/json': DogCreate;
				};
			};
			responses: {
				200: {
					content: {
						'application/json': Dog;
					};
				};
			};
		};
	};
	'/api/dogs/{dog_id}': {
		get: {
			parameters: {
				path: {
					dog_id: string;
				};
			};
			responses: {
				200: {
					content: {
						'application/json': Dog;
					};
				};
			};
		};
		put: {
			parameters: {
				path: {
					dog_id: string;
				};
			};
			requestBody: {
				content: {
					'application/json': DogUpdate;
				};
			};
			responses: {
				200: {
					content: {
						'application/json': Dog;
					};
				};
			};
		};
		delete: {
			parameters: {
				path: {
					dog_id: string;
				};
			};
			responses: {
				200: {
					content: {
						'application/json': { message: string };
					};
				};
			};
		};
	};
	'/api/dogs/{dog_id}/confirm': {
		post: {
			parameters: {
				path: {
					dog_id: string;
				};
			};
			responses: {
				200: {
					content: {
						'application/json': Dog;
					};
				};
			};
		};
	};
	'/api/dogs/{dog_id}/unconfirm': {
		post: {
			parameters: {
				path: {
					dog_id: string;
				};
			};
			responses: {
				200: {
					content: {
						'application/json': Dog;
					};
				};
			};
		};
	};
	'/api/dogs/{dog_id}/barks': {
		get: {
			parameters: {
				path: {
					dog_id: string;
				};
			};
			responses: {
				200: {
					content: {
						'application/json': Fingerprint[];
					};
				};
			};
		};
	};
	'/api/fingerprints': {
		get: {
			parameters: {
				query?: {
					dog_id?: string;
					tagged?: boolean;
					start_date?: string;
					end_date?: string;
					min_confidence?: number;
					page?: number;
					size?: number;
					sort_by?: string;
					sort_order?: string;
				};
			};
			responses: {
				200: {
					content: {
						'application/json': PaginatedFingerprints;
					};
				};
			};
		};
	};
	'/api/fingerprints/stats': {
		get: {
			responses: {
				200: {
					content: {
						'application/json': FingerprintStats;
					};
				};
			};
		};
	};
	'/api/fingerprints/{fingerprint_id}/tag': {
		post: {
			parameters: {
				path: {
					fingerprint_id: string;
				};
			};
			requestBody: {
				content: {
					'application/json': { dog_id: string };
				};
			};
			responses: {
				200: {
					content: {
						'application/json': Fingerprint;
					};
				};
			};
		};
	};
	'/api/barks/untagged': {
		get: {
			parameters: {
				query?: {
					limit?: number;
				};
			};
			responses: {
				200: {
					content: {
						'application/json': Fingerprint[];
					};
				};
			};
		};
	};
	'/api/evidence/stats': {
		get: {
			responses: {
				200: {
					content: {
						'application/json': EvidenceStats;
					};
				};
			};
		};
	};
	'/api/evidence/{filename}': {
		get: {
			parameters: {
				path: {
					filename: string;
				};
				query?: {
					format?: 'wav' | 'opus';
				};
			};
			responses: {
				200: {
					content: {
						'audio/wav': Blob;
						'audio/opus': Blob;
					};
				};
			};
		};
	};
	'/api/maintenance/purge-evidence': {
		post: {
			requestBody: {
				content: {
					'application/json': { before_date: string };
				};
			};
			responses: {
				200: {
					content: {
						'application/json': PurgeResult;
					};
				};
			};
		};
	};
	'/api/maintenance/purge-fingerprints': {
		post: {
			requestBody: {
				content: {
					'application/json': { before_date?: string; untagged_only?: boolean };
				};
			};
			responses: {
				200: {
					content: {
						'application/json': PurgeResult;
					};
				};
			};
		};
	};
	'/api/maintenance/recalculate-bark-counts': {
		post: {
			responses: {
				200: {
					content: {
						'application/json': RecalculateResult;
					};
				};
			};
		};
	};
}

// Domain types
export interface Dog {
	id: string;
	name: string;
	notes: string | null;
	emoji: string;
	is_confirmed: boolean;
	bark_count: number;
	created_at: string;
	updated_at: string;
}

export interface DogCreate {
	name: string;
	notes?: string;
	emoji?: string;
}

export interface DogUpdate {
	name?: string;
	notes?: string;
	emoji?: string;
}

export interface Fingerprint {
	id: string;
	timestamp: string;
	confidence: number;
	duration_ms: number;
	pitch_hz: number | null;
	dog_id: string | null;
	dog_name: string | null;
	evidence_file: string | null;
	created_at: string;
}

export interface PaginatedFingerprints {
	items: Fingerprint[];
	total: number;
	page: number;
	size: number;
	pages: number;
}

export interface FingerprintStats {
	total: number;
	tagged: number;
	untagged: number;
	by_dog: Record<string, number>;
}

export interface EvidenceStats {
	total_files: number;
	total_duration_seconds: number;
	oldest_file: string | null;
	newest_file: string | null;
}

export interface PurgeResult {
	deleted_count: number;
	message: string;
}

export interface RecalculateResult {
	updated_dogs: number;
	message: string;
}
