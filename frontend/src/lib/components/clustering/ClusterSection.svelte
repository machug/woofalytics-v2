<script lang="ts">
	/**
	 * ClusterSection - Main container for bark clustering analysis
	 * Manages clustering state, API calls, and dog creation flow
	 */
	import type { ClusterResult, ClusterSuggestion, DogCreate } from '$lib/api/types';
	import ClusterCard from './ClusterCard.svelte';
	import CreateDogFromClusterModal from './CreateDogFromClusterModal.svelte';

	interface Props {
		untaggedCount: number;
		onDataRefresh: () => void;
	}

	let { untaggedCount, onDataRefresh }: Props = $props();

	// Clustering state
	let clusterResult = $state<ClusterResult | null>(null);
	let isAnalyzing = $state(false);
	let error = $state<string | null>(null);
	let hasAnalyzed = $state(false);

	// Modal state
	let createModalOpen = $state(false);
	let selectedCluster = $state<ClusterSuggestion | null>(null);
	let isCreatingDog = $state(false);

	async function runClustering() {
		isAnalyzing = true;
		error = null;

		try {
			const response = await fetch('/api/fingerprints/cluster', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' }
			});

			if (!response.ok) {
				const errorData = await response.json().catch(() => ({}));
				throw new Error(errorData.detail || 'Clustering failed');
			}

			clusterResult = await response.json();
			hasAnalyzed = true;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Analysis failed';
			clusterResult = null;
		} finally {
			isAnalyzing = false;
		}
	}

	function openCreateDogModal(cluster: ClusterSuggestion) {
		selectedCluster = cluster;
		createModalOpen = true;
	}

	async function handleCreateDog(dogData: DogCreate) {
		if (!selectedCluster) return;

		isCreatingDog = true;

		try {
			const response = await fetch(
				`/api/fingerprints/cluster/${selectedCluster.cluster_id}/create-dog`,
				{
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify(dogData)
				}
			);

			if (!response.ok) {
				const errorData = await response.json().catch(() => ({}));
				throw new Error(errorData.detail || 'Failed to create dog');
			}

			// Success - close modal and update state
			const createdClusterId = selectedCluster.cluster_id;
			const clusterSize = selectedCluster.size;
			createModalOpen = false;
			selectedCluster = null;

			// Remove the created cluster from suggestions
			if (clusterResult) {
				clusterResult = {
					...clusterResult,
					suggestions: clusterResult.suggestions.filter((s) => s.cluster_id !== createdClusterId)
				};
			}

			// Refresh parent data (stats, dogs, fingerprints)
			onDataRefresh();

			// Show success message (if toast system exists, we'd use it here)
			console.log(`Dog profile created with ${clusterSize} barks`);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to create dog profile';
		} finally {
			isCreatingDog = false;
		}
	}

	function handleModalCancel() {
		selectedCluster = null;
	}

	// Computed values
	const canAnalyze = $derived(untaggedCount >= 3 && !isAnalyzing);
	const hasClusters = $derived(clusterResult && clusterResult.suggestions.length > 0);
</script>

<section class="cluster-section">
	<div class="section-header">
		<h2 class="section-title">
			<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<circle cx="12" cy="12" r="3" />
				<circle cx="4" cy="8" r="2" />
				<circle cx="20" cy="8" r="2" />
				<circle cx="4" cy="16" r="2" />
				<circle cx="20" cy="16" r="2" />
				<line x1="9.5" y1="10.5" x2="6" y2="9" />
				<line x1="14.5" y1="10.5" x2="18" y2="9" />
				<line x1="9.5" y1="13.5" x2="6" y2="15" />
				<line x1="14.5" y1="13.5" x2="18" y2="15" />
			</svg>
			Bark Clustering
		</h2>
		<button class="analyze-btn" onclick={runClustering} disabled={!canAnalyze}>
			{#if isAnalyzing}
				<div class="spinner"></div>
				Analyzing...
			{:else}
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<polygon points="5 3 19 12 5 21 5 3" />
				</svg>
				Analyze Untagged Barks
			{/if}
		</button>
	</div>

	<div class="section-body">
		{#if error}
			<div class="error-banner">
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<circle cx="12" cy="12" r="10" />
					<line x1="15" y1="9" x2="9" y2="15" />
					<line x1="9" y1="9" x2="15" y2="15" />
				</svg>
				<span>{error}</span>
				<button class="retry-btn" onclick={runClustering}>Retry</button>
			</div>
		{:else if !hasAnalyzed}
			<div class="initial-state">
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<circle cx="12" cy="12" r="10" />
					<path d="M12 16v-4M12 8h.01" />
				</svg>
				<div class="initial-text">
					<p>Analyze {untaggedCount} untagged barks to find patterns</p>
					<p class="hint">
						Clustering groups similar barks together, making it easy to create dog profiles
					</p>
				</div>
			</div>
		{:else if !hasClusters}
			<div class="empty-state">
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<circle cx="12" cy="12" r="10" />
					<line x1="8" y1="12" x2="16" y2="12" />
				</svg>
				<div class="empty-text">
					<p>No clusters found</p>
					<p class="hint">
						The barks are too diverse to group automatically. Try tagging some manually first.
					</p>
				</div>
			</div>
		{:else if clusterResult}
			<div class="results-info">
				<span class="results-count">{clusterResult.cluster_count} clusters found</span>
				{#if clusterResult.noise_count > 0}
					<span class="noise-info">{clusterResult.noise_count} barks too unique to cluster</span>
				{/if}
			</div>

			<div class="cluster-grid">
				{#each clusterResult.suggestions as cluster (cluster.cluster_id)}
					<ClusterCard {cluster} onCreateDog={() => openCreateDogModal(cluster)} />
				{/each}
			</div>
		{/if}
	</div>
</section>

{#if createModalOpen && selectedCluster}
	<CreateDogFromClusterModal
		bind:open={createModalOpen}
		cluster={selectedCluster}
		onSubmit={handleCreateDog}
		onCancel={handleModalCancel}
		{isCreatingDog}
	/>
{/if}

<style>
	.cluster-section {
		background: rgba(22, 27, 34, 0.6);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-lg);
		overflow: hidden;
	}

	.section-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: var(--space-md) var(--space-lg);
		background: var(--bg-surface);
		border-bottom: 1px solid var(--border-default);
	}

	.section-title {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.section-title svg {
		width: 18px;
		height: 18px;
		color: var(--accent-teal);
	}

	.analyze-btn {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		padding: var(--space-xs) var(--space-md);
		background: var(--accent-teal-dim);
		border: 1px solid var(--accent-teal);
		border-radius: var(--radius-sm);
		color: var(--accent-teal);
		font-size: 0.8rem;
		font-weight: 500;
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.analyze-btn:hover:not(:disabled) {
		background: var(--accent-teal);
		color: var(--bg-base);
	}

	.analyze-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.analyze-btn svg {
		width: 14px;
		height: 14px;
	}

	.section-body {
		padding: var(--space-lg);
	}

	.initial-state,
	.empty-state {
		display: flex;
		align-items: flex-start;
		gap: var(--space-md);
		padding: var(--space-lg);
		background: var(--bg-overlay);
		border: 1px dashed var(--border-default);
		border-radius: var(--radius-md);
	}

	.initial-state svg,
	.empty-state svg {
		width: 24px;
		height: 24px;
		color: var(--text-muted);
		flex-shrink: 0;
	}

	.initial-text,
	.empty-text {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}

	.initial-text p,
	.empty-text p {
		margin: 0;
		color: var(--text-secondary);
		font-size: 0.9rem;
	}

	.hint {
		color: var(--text-muted) !important;
		font-size: 0.8rem !important;
	}

	.error-banner {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-md);
		background: var(--accent-coral-dim);
		border: 1px solid rgba(248, 81, 73, 0.3);
		border-radius: var(--radius-md);
		color: var(--accent-coral);
		font-size: 0.875rem;
	}

	.error-banner svg {
		width: 18px;
		height: 18px;
		flex-shrink: 0;
	}

	.retry-btn {
		margin-left: auto;
		padding: var(--space-xs) var(--space-sm);
		background: transparent;
		border: 1px solid currentColor;
		border-radius: var(--radius-sm);
		color: inherit;
		font-size: 0.75rem;
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.retry-btn:hover {
		background: rgba(248, 81, 73, 0.2);
	}

	.results-info {
		display: flex;
		align-items: center;
		gap: var(--space-md);
		margin-bottom: var(--space-md);
		font-size: 0.875rem;
	}

	.results-count {
		color: var(--text-primary);
		font-weight: 500;
	}

	.noise-info {
		color: var(--text-muted);
		font-size: 0.8rem;
	}

	.cluster-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
		gap: var(--space-md);
	}

	.spinner {
		width: 14px;
		height: 14px;
		border: 2px solid var(--border-default);
		border-top-color: var(--accent-teal);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	@media (max-width: 640px) {
		.section-header {
			flex-direction: column;
			gap: var(--space-sm);
			align-items: stretch;
		}

		.analyze-btn {
			justify-content: center;
		}

		.cluster-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
