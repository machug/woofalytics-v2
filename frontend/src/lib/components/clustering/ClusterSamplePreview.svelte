<script lang="ts">
	/**
	 * ClusterSamplePreview - Audio preview for sample fingerprints in a cluster
	 * Fetches fingerprint details to get evidence filenames for audio playback
	 */
	import { api } from '$lib/api/client';
	import { AudioPlayer } from '$lib/components/fingerprints';

	interface Props {
		sampleIds: string[];
	}

	let { sampleIds }: Props = $props();

	interface SampleInfo {
		id: string;
		evidence_filename: string | null;
	}

	let samples = $state<SampleInfo[]>([]);
	let isLoading = $state(true);
	let error = $state<string | null>(null);

	// Fetch fingerprint details to get evidence filenames
	async function loadSamples() {
		if (sampleIds.length === 0) {
			samples = [];
			isLoading = false;
			return;
		}

		isLoading = true;
		error = null;

		try {
			// Fetch fingerprints list and filter by sample IDs
			// The API returns fingerprints with evidence_filename field
			const response = await api.GET('/api/fingerprints', {
				params: {
					query: {
						limit: 100
					}
				}
			});

			if (response.error) {
				throw new Error('Failed to fetch fingerprints');
			}

			const allFingerprints = response.data?.items ?? [];

			// Filter to just the sample IDs and extract evidence filenames
			const sampleSet = new Set(sampleIds);
			samples = allFingerprints
				.filter((fp) => sampleSet.has(fp.id))
				.map((fp) => ({
					id: fp.id,
					evidence_filename: fp.evidence_filename ?? null
				}))
				.slice(0, 3); // Max 3 samples
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load samples';
			samples = [];
		} finally {
			isLoading = false;
		}
	}

	// Load samples when component mounts or sampleIds change
	$effect(() => {
		loadSamples();
	});

	// Filter to samples that have evidence files
	const playableSamples = $derived(samples.filter((s) => s.evidence_filename));
</script>

<div class="sample-preview">
	{#if isLoading}
		<div class="loading">
			<div class="spinner"></div>
			<span>Loading samples...</span>
		</div>
	{:else if error}
		<div class="error">
			<span>{error}</span>
		</div>
	{:else if playableSamples.length === 0}
		<div class="no-samples">
			<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<path d="M9 18V5l12-2v13" />
				<circle cx="6" cy="18" r="3" />
				<circle cx="18" cy="16" r="3" />
			</svg>
			<span>No audio available</span>
		</div>
	{:else}
		<div class="samples-list">
			{#each playableSamples as sample, i (sample.id)}
				<div class="sample-item">
					<span class="sample-label">Sample {i + 1}</span>
					<AudioPlayer src={sample.evidence_filename!} />
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.sample-preview {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
	}

	.loading,
	.error,
	.no-samples {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-sm);
		color: var(--text-muted);
		font-size: 0.8rem;
	}

	.error {
		color: var(--accent-coral);
	}

	.no-samples svg {
		width: 16px;
		height: 16px;
		opacity: 0.5;
	}

	.samples-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}

	.sample-item {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.sample-label {
		font-size: 0.7rem;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
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
</style>
