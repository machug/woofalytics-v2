<script lang="ts">
	/**
	 * ClusterCard - Display a cluster suggestion with stats and actions
	 */
	import type { ClusterSuggestion } from '$lib/api/types';
	import ClusterSamplePreview from './ClusterSamplePreview.svelte';

	interface Props {
		cluster: ClusterSuggestion;
		onCreateDog: () => void;
	}

	let { cluster, onCreateDog }: Props = $props();

	// Format date range for display
	function formatDateRange(firstSeen: string | null, lastSeen: string | null): string {
		if (!firstSeen || !lastSeen) return 'Unknown';

		const first = new Date(firstSeen);
		const last = new Date(lastSeen);
		const sameDay = first.toDateString() === last.toDateString();

		const formatDate = (d: Date) =>
			d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
		const formatTime = (d: Date) =>
			d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });

		if (sameDay) {
			return `${formatDate(first)}, ${formatTime(first)} - ${formatTime(last)}`;
		}
		return `${formatDate(first)} - ${formatDate(last)}`;
	}

	// Determine coherence level for styling
	const coherenceLevel = $derived(
		cluster.coherence_score >= 0.8 ? 'high' : cluster.coherence_score >= 0.6 ? 'medium' : 'low'
	);
</script>

<article class="cluster-card" aria-label="Cluster with {cluster.size} barks">
	<div class="card-header">
		<div class="size-badge">
			<span class="size-value">{cluster.size}</span>
			<span class="size-label">barks</span>
		</div>
		<div class="coherence-badge" data-level={coherenceLevel}>
			<span class="coherence-label">Quality</span>
			<span class="coherence-value">{Math.round(cluster.coherence_score * 100)}%</span>
		</div>
	</div>

	<div class="card-stats">
		{#if cluster.first_seen && cluster.last_seen}
			<div class="stat-row">
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
					<line x1="16" y1="2" x2="16" y2="6" />
					<line x1="8" y1="2" x2="8" y2="6" />
					<line x1="3" y1="10" x2="21" y2="10" />
				</svg>
				<span class="stat-value">{formatDateRange(cluster.first_seen, cluster.last_seen)}</span>
			</div>
		{/if}

		{#if cluster.avg_pitch_hz}
			<div class="stat-row">
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<path d="M2 12h2l3-9 4 18 3-9 2 0" />
				</svg>
				<span class="stat-value">{Math.round(cluster.avg_pitch_hz)} Hz avg</span>
			</div>
		{/if}

		{#if cluster.avg_duration_ms}
			<div class="stat-row">
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<circle cx="12" cy="12" r="10" />
					<polyline points="12 6 12 12 16 14" />
				</svg>
				<span class="stat-value">{(cluster.avg_duration_ms / 1000).toFixed(2)}s avg</span>
			</div>
		{/if}
	</div>

	{#if cluster.sample_ids.length > 0}
		<div class="card-samples">
			<span class="samples-header">Sample barks</span>
			<ClusterSamplePreview sampleIds={cluster.sample_ids} />
		</div>
	{/if}

	<button class="create-dog-btn" onclick={onCreateDog}>
		<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
			<path d="M12 5v14M5 12h14" />
		</svg>
		Create Dog Profile
	</button>
</article>

<style>
	.cluster-card {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
		padding: var(--space-md);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
		transition:
			transform var(--transition-fast),
			box-shadow var(--transition-fast);
	}

	.cluster-card:hover {
		transform: translateY(-2px);
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
	}

	.card-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
	}

	.size-badge {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2px;
	}

	.size-value {
		font-size: 1.5rem;
		font-weight: 700;
		font-family: 'JetBrains Mono', monospace;
		color: var(--text-primary);
		line-height: 1;
	}

	.size-label {
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.coherence-badge {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2px;
		padding: var(--space-xs) var(--space-sm);
		border-radius: var(--radius-sm);
	}

	.coherence-badge[data-level='high'] {
		background: var(--accent-teal-dim);
		border: 1px solid var(--accent-teal);
	}

	.coherence-badge[data-level='high'] .coherence-value {
		color: var(--accent-teal);
	}

	.coherence-badge[data-level='medium'] {
		background: var(--accent-amber-dim);
		border: 1px solid var(--accent-amber);
	}

	.coherence-badge[data-level='medium'] .coherence-value {
		color: var(--accent-amber);
	}

	.coherence-badge[data-level='low'] {
		background: rgba(100, 116, 139, 0.2);
		border: 1px solid #64748b;
	}

	.coherence-badge[data-level='low'] .coherence-value {
		color: #64748b;
	}

	.coherence-label {
		font-size: 0.6rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.coherence-value {
		font-size: 0.875rem;
		font-weight: 600;
		font-family: 'JetBrains Mono', monospace;
	}

	.card-stats {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}

	.stat-row {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		color: var(--text-secondary);
		font-size: 0.8rem;
	}

	.stat-row svg {
		width: 14px;
		height: 14px;
		flex-shrink: 0;
		opacity: 0.6;
	}

	.stat-value {
		font-family: 'JetBrains Mono', monospace;
	}

	.card-samples {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
		padding-top: var(--space-sm);
		border-top: 1px solid var(--border-muted);
	}

	.samples-header {
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.create-dog-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-xs);
		width: 100%;
		padding: var(--space-sm) var(--space-md);
		background: var(--accent-amber-dim);
		border: 1px solid var(--accent-amber);
		border-radius: var(--radius-sm);
		color: var(--accent-amber);
		font-size: 0.875rem;
		font-weight: 500;
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.create-dog-btn:hover {
		background: var(--accent-amber);
		color: var(--bg-base);
	}

	.create-dog-btn svg {
		width: 16px;
		height: 16px;
	}
</style>
