<script lang="ts">
	/**
	 * CreateDogFromClusterModal - Modal for creating a dog profile from a cluster
	 */
	import type { ClusterSuggestion, DogCreate } from '$lib/api/types';
	import Modal from '$lib/components/ui/Modal.svelte';
	import DogForm from '$lib/components/dogs/DogForm.svelte';

	interface Props {
		open: boolean;
		cluster: ClusterSuggestion;
		onSubmit: (data: DogCreate) => void;
		onCancel: () => void;
		isSubmitting: boolean;
	}

	let { open = $bindable(false), cluster, onSubmit, onCancel, isSubmitting }: Props = $props();

	function handleFormSubmit(data: DogCreate) {
		onSubmit(data);
	}

	function handleCancel() {
		open = false;
		onCancel();
	}
</script>

<Modal bind:open title="Create Dog from Cluster">
	{#snippet children()}
		<div class="cluster-summary">
			<div class="summary-header">
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<circle cx="12" cy="12" r="10" />
					<path d="M12 16v-4M12 8h.01" />
				</svg>
				<span>Create a new dog profile from <strong>{cluster.size} barks</strong></span>
			</div>
			<div class="summary-stats">
				<div class="stat">
					<span class="stat-label">Coherence</span>
					<span class="stat-value">{Math.round(cluster.coherence_score * 100)}%</span>
				</div>
				{#if cluster.avg_pitch_hz}
					<div class="stat">
						<span class="stat-label">Avg Pitch</span>
						<span class="stat-value">{Math.round(cluster.avg_pitch_hz)} Hz</span>
					</div>
				{/if}
				{#if cluster.avg_duration_ms}
					<div class="stat">
						<span class="stat-label">Avg Duration</span>
						<span class="stat-value">{(cluster.avg_duration_ms / 1000).toFixed(2)}s</span>
					</div>
				{/if}
			</div>
		</div>

		<div class="form-container" class:submitting={isSubmitting}>
			<DogForm onSubmit={handleFormSubmit} onCancel={handleCancel} />

			{#if isSubmitting}
				<div class="submitting-overlay">
					<div class="spinner"></div>
					<span>Creating dog profile...</span>
				</div>
			{/if}
		</div>
	{/snippet}
</Modal>

<style>
	.cluster-summary {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
		padding: var(--space-md);
		background: var(--accent-teal-dim);
		border: 1px solid var(--accent-teal);
		border-radius: var(--radius-sm);
		margin-bottom: var(--space-md);
	}

	.summary-header {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		color: var(--text-primary);
		font-size: 0.9rem;
	}

	.summary-header svg {
		width: 18px;
		height: 18px;
		color: var(--accent-teal);
		flex-shrink: 0;
	}

	.summary-header strong {
		color: var(--accent-teal);
	}

	.summary-stats {
		display: flex;
		gap: var(--space-md);
		padding-top: var(--space-xs);
	}

	.stat {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.stat-label {
		font-size: 0.65rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.stat-value {
		font-size: 0.8rem;
		font-weight: 600;
		font-family: 'JetBrains Mono', monospace;
		color: var(--text-secondary);
	}

	.form-container {
		position: relative;
	}

	.form-container.submitting {
		opacity: 0.5;
		pointer-events: none;
	}

	.submitting-overlay {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--space-sm);
		background: rgba(13, 17, 23, 0.8);
		border-radius: var(--radius-sm);
		color: var(--text-primary);
		font-size: 0.9rem;
	}

	.spinner {
		width: 24px;
		height: 24px;
		border: 3px solid var(--border-default);
		border-top-color: var(--accent-teal);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
</style>
