<script lang="ts">
	/**
	 * Fingerprints Explorer Page
	 * Browse, filter, and explore bark fingerprints with audio playback
	 */

	import { page } from '$app/stores';
	import { browser } from '$app/environment';
	import { api, fetchApi } from '$lib/api/client';
	import type { Dog, Fingerprint, PaginatedFingerprints, FingerprintStats } from '$lib/api/types';
	import FilterPanel, { type Filters } from '$lib/components/fingerprints/FilterPanel.svelte';
	import FingerprintTable from '$lib/components/fingerprints/FingerprintTable.svelte';
	import Pagination from '$lib/components/fingerprints/Pagination.svelte';

	// State
	let fingerprints = $state<Fingerprint[]>([]);
	let dogs = $state<Dog[]>([]);
	let stats = $state<FingerprintStats | null>(null);
	let totalItems = $state(0);
	let totalPages = $state(1);
	let currentPage = $state(1);
	let pageSize = $state(50);
	let sortBy = $state('timestamp');
	let sortOrder = $state<'asc' | 'desc'>('desc');
	let isLoading = $state(true);
	let error = $state<string | null>(null);

	// Filters state
	let filters = $state<Filters>({
		dog_id: '',
		start_date: '',
		end_date: '',
		tagged: null,
		min_confidence: 0
	});

	// Debounce timer for filter application
	let filterDebounceTimer: ReturnType<typeof setTimeout> | null = null;

	// Initialize from URL params on mount (runs once)
	let initialized = false;
	$effect(() => {
		if (browser && !initialized) {
			initialized = true;
			initFromUrl();
		}
	});

	// Sync URL when filters/pagination change - use history API directly to avoid SvelteKit navigation issues
	const syncUrl = () => {
		if (!browser) return;

		const params = new URLSearchParams();

		if (currentPage > 1) params.set('page', String(currentPage));
		if (filters.dog_id) params.set('dog_id', filters.dog_id);
		if (filters.tagged !== null) params.set('tagged', String(filters.tagged));
		if (filters.start_date) params.set('start_date', filters.start_date);
		if (filters.end_date) params.set('end_date', filters.end_date);
		if (filters.min_confidence > 0) params.set('min_confidence', String(filters.min_confidence));
		if (sortBy !== 'timestamp') params.set('sort_by', sortBy);
		if (sortOrder !== 'desc') params.set('sort_order', sortOrder);

		const queryString = params.toString();
		const newUrl = queryString ? `/fingerprints?${queryString}` : '/fingerprints';

		// Use history.replaceState directly to avoid interfering with SvelteKit navigation
		history.replaceState(history.state, '', newUrl);
	};

	// Initialize state from URL
	const initFromUrl = () => {
		const params = $page.url.searchParams;

		currentPage = parseInt(params.get('page') || '1', 10);
		filters.dog_id = params.get('dog_id') || '';
		filters.start_date = params.get('start_date') || '';
		filters.end_date = params.get('end_date') || '';
		filters.min_confidence = parseFloat(params.get('min_confidence') || '0');

		const taggedParam = params.get('tagged');
		if (taggedParam === 'true') filters.tagged = true;
		else if (taggedParam === 'false') filters.tagged = false;
		else filters.tagged = null;

		sortBy = params.get('sort_by') || 'timestamp';
		sortOrder = (params.get('sort_order') as 'asc' | 'desc') || 'desc';

		// Load initial data
		loadDogs();
		loadStats();
		loadFingerprints();
	};

	// Load dogs for filter dropdown
	const loadDogs = async () => {
		try {
			const response = await api.GET('/api/dogs');
			if (response.data) {
				dogs = response.data;
			}
		} catch (e) {
			console.error('Failed to load dogs:', e);
		}
	};

	// Load stats
	const loadStats = async () => {
		try {
			const response = await api.GET('/api/fingerprints/stats');
			if (response.data) {
				stats = response.data;
			}
		} catch (e) {
			console.error('Failed to load stats:', e);
		}
	};

	// Load fingerprints with current filters
	const loadFingerprints = async () => {
		isLoading = true;
		error = null;

		try {
			// API uses offset-based pagination (limit/offset), not page-based
			const offset = (currentPage - 1) * pageSize;
			const queryParams: Record<string, unknown> = {
				limit: pageSize,
				offset: offset
			};

			if (filters.dog_id) queryParams.dog_id = filters.dog_id;
			if (filters.tagged !== null) queryParams.tagged = filters.tagged;
			if (filters.start_date) queryParams.start_date = filters.start_date;
			if (filters.end_date) queryParams.end_date = filters.end_date;
			if (filters.min_confidence > 0) queryParams.min_confidence = filters.min_confidence;

			const response = await api.GET('/api/fingerprints', {
				params: { query: queryParams as any }
			});

			if (response.data) {
				const data = response.data;
				fingerprints = data.items;
				totalItems = data.total;
				// Calculate pages from total and limit
				totalPages = Math.ceil(data.total / pageSize);
				// currentPage stays as-is since we control it client-side
			}
		} catch (e) {
			console.error('Failed to load fingerprints:', e);
			error = 'Failed to load fingerprints. Please try again.';
			fingerprints = [];
		} finally {
			isLoading = false;
		}
	};

	// Handle filter apply
	const handleFilterApply = (newFilters: Filters) => {
		filters = newFilters;
		currentPage = 1; // Reset to first page on filter change
		loadFingerprints();
		syncUrl();
	};

	// Handle filter reset
	const handleFilterReset = () => {
		filters = {
			dog_id: '',
			start_date: '',
			end_date: '',
			tagged: null,
			min_confidence: 0
		};
		currentPage = 1;
		loadFingerprints();
		syncUrl();
	};

	// Handle sort change
	const handleSort = (column: string) => {
		if (sortBy === column) {
			// Toggle order
			sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
		} else {
			sortBy = column;
			sortOrder = 'desc';
		}
		loadFingerprints();
		syncUrl();
	};

	// Handle page change
	const handlePageChange = (newPage: number) => {
		currentPage = newPage;
		loadFingerprints();
		syncUrl();
	};

	// Handle untag a fingerprint
	const handleUntag = async (fingerprint: Fingerprint) => {
		try {
			await api.POST('/api/barks/{bark_id}/untag', {
				params: { path: { bark_id: fingerprint.id } }
			});

			// Refresh data
			loadFingerprints();
			loadStats();
		} catch (e) {
			console.error('Failed to untag bark:', e);
			error = 'Failed to untag bark. Please try again.';
		}
	};

	// Computed stats display values
	// API returns { dogs, fingerprints, untagged, clusters }
	const statsTotal = $derived(stats?.fingerprints ?? 0);
	const statsTagged = $derived((stats?.fingerprints ?? 0) - (stats?.untagged ?? 0));
	const statsUntagged = $derived(stats?.untagged ?? 0);
	const statsDogs = $derived(stats?.dogs ?? 0);
</script>

<svelte:head>
	<title>Fingerprints Explorer - Woofalytics</title>
</svelte:head>

<div class="fingerprints-page">
	<!-- Header -->
	<header class="page-header">
		<div class="header-content">
			<svg class="header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<path
					d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04l.054-.09A13.916 13.916 0 008 11a4 4 0 118 0c0 1.017-.07 2.019-.203 3m-2.118 6.844A21.88 21.88 0 0015.171 17m3.839 1.132c.645-2.266.99-4.659.99-7.132A8 8 0 008 4.07M3 15.364c.64-1.319 1-2.8 1-4.364 0-1.457.39-2.823 1.07-4"
				/>
			</svg>
			<h1>Fingerprints Explorer</h1>
		</div>
	</header>

	<!-- Stats Row -->
	<div class="stats-row">
		<div class="stat-pill stat-pill--total">
			<span class="stat-pill-value">{statsTotal}</span>
			<span class="stat-pill-label">Total Fingerprints</span>
		</div>
		<div class="stat-pill stat-pill--tagged">
			<span class="stat-pill-value">{statsTagged}</span>
			<span class="stat-pill-label">Tagged</span>
		</div>
		<div class="stat-pill stat-pill--untagged">
			<span class="stat-pill-value">{statsUntagged}</span>
			<span class="stat-pill-label">Untagged</span>
		</div>
		<div class="stat-pill stat-pill--dogs">
			<span class="stat-pill-value">{statsDogs}</span>
			<span class="stat-pill-label">Dogs</span>
		</div>
	</div>

	<!-- Main Content -->
	<main class="fingerprints-layout">
		<!-- Fingerprints Table Section -->
		<section class="fp-section">
			<div class="fp-section-header">
				<h2 class="fp-section-title">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path
							d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04l.054-.09A13.916 13.916 0 008 11a4 4 0 118 0c0 1.017-.07 2.019-.203 3m-2.118 6.844A21.88 21.88 0 0015.171 17m3.839 1.132c.645-2.266.99-4.659.99-7.132A8 8 0 008 4.07M3 15.364c.64-1.319 1-2.8 1-4.364 0-1.457.39-2.823 1.07-4"
						/>
					</svg>
					Fingerprints
				</h2>
			</div>

			<!-- Filter Panel -->
			<FilterPanel
				bind:filters
				{dogs}
				onApply={handleFilterApply}
				onReset={handleFilterReset}
			/>

			<!-- Error State -->
			{#if error}
				<div class="error-banner">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<circle cx="12" cy="12" r="10" />
						<line x1="15" y1="9" x2="9" y2="15" />
						<line x1="9" y1="9" x2="15" y2="15" />
					</svg>
					<span>{error}</span>
					<button class="btn btn-sm btn-outline" onclick={loadFingerprints}>Retry</button>
				</div>
			{/if}

			<!-- Table -->
			<div class="fp-section-body">
				<FingerprintTable
					{fingerprints}
					{sortBy}
					{sortOrder}
					onSort={handleSort}
					onUntag={handleUntag}
					{isLoading}
				/>
			</div>

			<!-- Pagination -->
			{#if !isLoading && fingerprints.length > 0}
				<Pagination
					page={currentPage}
					{totalPages}
					{totalItems}
					{pageSize}
					onPageChange={handlePageChange}
				/>
			{/if}
		</section>
	</main>
</div>

<style>
	.fingerprints-page {
		--card-bg: rgba(22, 27, 34, 0.6);
		--card-bg-hover: rgba(28, 33, 40, 0.8);
	}

	/* Header */
	.page-header {
		margin-bottom: var(--space-lg);
	}

	.header-content {
		display: flex;
		align-items: center;
		gap: var(--space-md);
	}

	.header-icon {
		width: 32px;
		height: 32px;
		color: var(--accent-teal);
	}

	.page-header h1 {
		font-size: 1.75rem;
		font-weight: 700;
		color: var(--text-primary);
		margin: 0;
	}

	/* Stats Row */
	.stats-row {
		display: flex;
		gap: var(--space-md);
		margin-bottom: var(--space-lg);
		padding: var(--space-md) var(--space-lg);
		background: var(--card-bg);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-lg);
		backdrop-filter: blur(20px);
		flex-wrap: wrap;
	}

	.stat-pill {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-xs) var(--space-md);
		background: var(--bg-overlay);
		border-radius: var(--radius-full);
	}

	.stat-pill-value {
		font-size: 1.25rem;
		font-weight: 700;
		font-family: 'JetBrains Mono', monospace;
		color: var(--text-primary);
	}

	.stat-pill-label {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.stat-pill--total .stat-pill-value {
		color: var(--accent-teal);
	}
	.stat-pill--tagged .stat-pill-value {
		color: var(--accent-amber);
	}
	.stat-pill--untagged .stat-pill-value {
		color: var(--accent-coral);
	}
	.stat-pill--dogs .stat-pill-value {
		color: var(--accent-blue);
	}

	/* Main Layout */
	.fingerprints-layout {
		display: flex;
		flex-direction: column;
		gap: var(--space-lg);
		flex: 1;
	}

	/* Section Panels */
	.fp-section {
		display: flex;
		flex-direction: column;
		background: var(--card-bg);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-lg);
		backdrop-filter: blur(20px);
		overflow: hidden;
	}

	.fp-section-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--space-md) var(--space-lg);
		border-bottom: 1px solid var(--border-muted);
		background: rgba(0, 0, 0, 0.2);
		flex-wrap: wrap;
		gap: var(--space-sm);
	}

	.fp-section-title {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.fp-section-title svg {
		width: 18px;
		height: 18px;
		color: var(--accent-teal);
	}

	.fp-section-body {
		flex: 1;
		padding: var(--space-md);
		overflow-x: auto;
	}

	/* Error Banner */
	.error-banner {
		display: flex;
		align-items: center;
		gap: var(--space-md);
		padding: var(--space-md) var(--space-lg);
		background: rgba(248, 81, 73, 0.1);
		border-bottom: 1px solid rgba(248, 81, 73, 0.3);
		color: var(--accent-coral);
		font-size: 0.875rem;
	}

	.error-banner svg {
		width: 20px;
		height: 20px;
		flex-shrink: 0;
	}

	.error-banner span {
		flex: 1;
	}

	/* Responsive */
	@media (max-width: 768px) {
		.stats-row {
			gap: var(--space-sm);
			padding: var(--space-sm) var(--space-md);
		}

		.stat-pill {
			flex: 1;
			min-width: 140px;
		}

		.page-header h1 {
			font-size: 1.25rem;
		}
	}
</style>
