<script lang="ts">
	/**
	 * ExportPreviewModal - Preview and download bark event data exports
	 * Supports JSON and CSV formats with filtering options
	 */

	import Modal from '$lib/components/ui/Modal.svelte';
	import { api } from '$lib/api/client';

	interface ExportStats {
		total_count: number;
		date_range: { start: string; end: string } | null;
		filters_applied: Record<string, unknown>;
	}

	interface Props {
		open: boolean;
		startDate: string;
		endDate: string;
	}

	let { open = $bindable(false), startDate, endDate }: Props = $props();

	let format = $state<'json' | 'csv'>('csv');
	let minConfidence = $state(0);
	let stats = $state<ExportStats | null>(null);
	let loading = $state(false);
	let downloading = $state(false);
	let error = $state<string | null>(null);

	// Fetch export stats when modal opens or filters change
	async function fetchStats() {
		loading = true;
		error = null;

		try {
			const response = await api.GET('/api/export/stats', {
				params: {
					query: {
						start_date: startDate || undefined,
						end_date: endDate || undefined,
						min_confidence: minConfidence > 0 ? minConfidence : undefined
					}
				}
			});

			if (response.error) {
				error = 'Failed to fetch export stats';
				return;
			}

			stats = response.data as ExportStats;
		} catch (err) {
			error = 'Failed to connect to API';
		} finally {
			loading = false;
		}
	}

	// Handle download
	async function handleDownload() {
		downloading = true;
		error = null;

		try {
			const endpoint = format === 'csv' ? '/api/export/csv' : '/api/export/json';
			const params = new URLSearchParams();
			if (startDate) params.set('start_date', startDate);
			if (endDate) params.set('end_date', endDate);
			if (minConfidence > 0) params.set('min_confidence', minConfidence.toString());

			// Fetch raw response for download
			const apiBase = import.meta.env.DEV ? '' : '';
			const url = `${apiBase}${endpoint}?${params.toString()}`;
			const response = await fetch(url);

			if (!response.ok) {
				throw new Error(`HTTP ${response.status}`);
			}

			// Create blob and download
			const blob = await response.blob();
			const filename = `bark-events-${startDate || 'all'}-to-${endDate || 'now'}.${format}`;

			const link = document.createElement('a');
			link.href = URL.createObjectURL(blob);
			link.download = filename;
			document.body.appendChild(link);
			link.click();
			document.body.removeChild(link);
			URL.revokeObjectURL(link.href);

			open = false;
		} catch (err) {
			error = 'Download failed. Please try again.';
		} finally {
			downloading = false;
		}
	}

	// Fetch stats when modal opens
	$effect(() => {
		if (open) {
			fetchStats();
		}
	});

	// Re-fetch stats when confidence filter changes
	$effect(() => {
		if (open && minConfidence !== undefined) {
			fetchStats();
		}
	});

	// Format file size estimate
	function estimateSize(count: number, fmt: 'json' | 'csv'): string {
		// Rough estimates: ~500 bytes per JSON record, ~200 per CSV row
		const bytesPerRecord = fmt === 'json' ? 500 : 200;
		const bytes = count * bytesPerRecord;

		if (bytes < 1024) return `~${bytes} B`;
		if (bytes < 1024 * 1024) return `~${Math.round(bytes / 1024)} KB`;
		return `~${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	const confidencePercent = $derived(Math.round(minConfidence * 100));
</script>

<Modal bind:open title="Export Bark Events">
	{#snippet children()}
		<div class="export-content">
			{#if error}
				<div class="error-banner">
					<span class="error-icon">⚠️</span>
					<span class="error-text">{error}</span>
				</div>
			{/if}

			<!-- Date Range Display -->
			<div class="info-row">
				<span class="info-label">Date Range</span>
				<span class="info-value">
					{#if startDate && endDate}
						{startDate} to {endDate}
					{:else if startDate}
						From {startDate}
					{:else if endDate}
						Until {endDate}
					{:else}
						All time
					{/if}
				</span>
			</div>

			<!-- Format Selection -->
			<div class="format-selection">
				<span class="format-label">Export Format</span>
				<div class="format-buttons">
					<button
						class="format-btn"
						class:active={format === 'csv'}
						onclick={() => (format = 'csv')}
					>
						<span class="format-icon">📄</span>
						<span class="format-name">CSV</span>
						<span class="format-desc">Spreadsheet compatible</span>
					</button>
					<button
						class="format-btn"
						class:active={format === 'json'}
						onclick={() => (format = 'json')}
					>
						<span class="format-icon">📋</span>
						<span class="format-name">JSON</span>
						<span class="format-desc">Full metadata</span>
					</button>
				</div>
			</div>

			<!-- Confidence Filter -->
			<div class="confidence-filter">
				<label class="filter-label" for="export-confidence">
					Min Confidence: <span class="confidence-value">{confidencePercent}%</span>
				</label>
				<input
					type="range"
					id="export-confidence"
					class="filter-slider"
					min="0"
					max="1"
					step="0.05"
					bind:value={minConfidence}
				/>
			</div>

			<!-- Preview Stats -->
			<div class="preview-stats" class:loading>
				<div class="stat-row">
					<span class="stat-label">Records to export</span>
					<span class="stat-value">{stats?.total_count.toLocaleString() ?? '—'}</span>
				</div>
				<div class="stat-row">
					<span class="stat-label">Estimated file size</span>
					<span class="stat-value">
						{stats ? estimateSize(stats.total_count, format) : '—'}
					</span>
				</div>
			</div>

			{#if stats && stats.total_count === 0}
				<div class="empty-warning">
					<span class="warning-icon">ℹ️</span>
					<span class="warning-text">No records match the current filters</span>
				</div>
			{/if}
		</div>
	{/snippet}

	{#snippet actions()}
		<button class="btn btn-ghost" onclick={() => (open = false)}>Cancel</button>
		<button
			class="btn btn-teal"
			onclick={handleDownload}
			disabled={downloading || loading || !stats || stats.total_count === 0}
		>
			{#if downloading}
				Downloading...
			{:else}
				Download {format.toUpperCase()}
			{/if}
		</button>
	{/snippet}
</Modal>

<style>
	.export-content {
		display: flex;
		flex-direction: column;
		gap: var(--space-lg);
		min-width: 360px;
	}

	.error-banner {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-sm) var(--space-md);
		background: rgba(239, 68, 68, 0.1);
		border: 1px solid rgba(239, 68, 68, 0.3);
		border-radius: var(--radius-sm);
		color: #f87171;
		font-size: 0.85rem;
	}

	.info-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: var(--space-sm) var(--space-md);
		background: var(--bg-overlay);
		border-radius: var(--radius-sm);
	}

	.info-label {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.info-value {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.85rem;
		color: var(--text-primary);
	}

	.format-selection {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
	}

	.format-label {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.format-buttons {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--space-sm);
	}

	.format-btn {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-xs);
		padding: var(--space-md);
		background: var(--bg-overlay);
		border: 2px solid var(--border-default);
		border-radius: var(--radius-md);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.format-btn:hover {
		border-color: var(--accent-teal);
	}

	.format-btn.active {
		border-color: var(--accent-teal);
		background: var(--accent-teal-dim);
	}

	.format-icon {
		font-size: 1.5rem;
	}

	.format-name {
		font-weight: 600;
		color: var(--text-primary);
	}

	.format-desc {
		font-size: 0.7rem;
		color: var(--text-muted);
	}

	.confidence-filter {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
	}

	.filter-label {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.confidence-value {
		color: var(--accent-teal);
		font-family: 'JetBrains Mono', monospace;
	}

	.filter-slider {
		-webkit-appearance: none;
		appearance: none;
		width: 100%;
		height: 6px;
		background: var(--border-default);
		border-radius: 3px;
		outline: none;
		cursor: pointer;
	}

	.filter-slider::-webkit-slider-thumb {
		-webkit-appearance: none;
		appearance: none;
		width: 16px;
		height: 16px;
		background: var(--accent-teal);
		border-radius: 50%;
		cursor: pointer;
	}

	.filter-slider::-moz-range-thumb {
		width: 16px;
		height: 16px;
		background: var(--accent-teal);
		border-radius: 50%;
		border: none;
		cursor: pointer;
	}

	.preview-stats {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
		padding: var(--space-md);
		background: var(--accent-teal-dim);
		border-radius: var(--radius-sm);
		border-left: 3px solid var(--accent-teal);
	}

	.preview-stats.loading {
		opacity: 0.6;
	}

	.stat-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.stat-label {
		font-size: 0.8rem;
		color: var(--text-secondary);
	}

	.stat-value {
		font-family: 'JetBrains Mono', monospace;
		font-weight: 600;
		color: var(--text-primary);
	}

	.empty-warning {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-sm) var(--space-md);
		background: rgba(245, 158, 11, 0.1);
		border: 1px solid rgba(245, 158, 11, 0.3);
		border-radius: var(--radius-sm);
	}

	.warning-text {
		font-size: 0.85rem;
		color: var(--accent-amber);
	}
</style>
