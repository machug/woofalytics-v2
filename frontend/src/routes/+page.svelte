<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { WaveformVisualizer, ParticleSystem, BarkGauge, RecentBarks } from '$lib/components/dashboard';
	import { Card } from '$lib/components/ui';
	import { api, fetchApi } from '$lib/api/client';
	import type { Dog, FingerprintStats, EvidenceStats } from '$lib/api/types';
	import { startBarkListener, stopBarkListener, barkStore } from '$lib/stores/bark';
	import { startAudioListener, stopAudioListener } from '$lib/stores/audio';
	import { audioConnectionState } from '$lib/stores/websocket';

	// State
	let dogs = $state<Dog[]>([]);
	let fingerprintStats = $state<FingerprintStats | null>(null);
	let evidenceStats = $state<EvidenceStats | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Derived
	let connectionState = $derived($audioConnectionState);

	async function loadData() {
		try {
			loading = true;
			error = null;

			const [dogsResult, fpStatsResult, evStatsResult] = await Promise.all([
				fetchApi(() => api.GET('/api/dogs')),
				fetchApi(() => api.GET('/api/fingerprints/stats')),
				fetchApi(() => api.GET('/api/evidence/stats'))
			]);

			dogs = dogsResult;
			fingerprintStats = fpStatsResult;
			evidenceStats = evStatsResult;

			// Update total bark count from API
			if (fingerprintStats) {
				barkStore.setTotalCount(fingerprintStats.total);
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load dashboard data';
		} finally {
			loading = false;
		}
	}

	function formatNumber(num: number): string {
		return num.toLocaleString();
	}

	function formatDuration(seconds: number): string {
		const hours = Math.floor(seconds / 3600);
		const minutes = Math.floor((seconds % 3600) / 60);
		if (hours > 0) {
			return `${hours}h ${minutes}m`;
		}
		return `${minutes}m`;
	}

	onMount(() => {
		loadData();
		startBarkListener();
		startAudioListener();
	});

	onDestroy(() => {
		stopBarkListener();
		stopAudioListener();
	});
</script>

<svelte:head>
	<title>Dashboard | Woofalytics</title>
</svelte:head>

<div class="dashboard">
	<header class="dashboard-header">
		<div class="title-section">
			<h1 class="page-title">Mission Control</h1>
			<p class="page-subtitle">Real-time bark detection monitoring</p>
		</div>
		<div class="connection-status" class:connected={connectionState === 'connected'}>
			<span class="status-dot"></span>
			<span class="status-text">
				{#if connectionState === 'connected'}
					LIVE
				{:else if connectionState === 'connecting' || connectionState === 'reconnecting'}
					CONNECTING...
				{:else}
					OFFLINE
				{/if}
			</span>
		</div>
	</header>

	{#if error}
		<div class="error-banner">
			<span class="error-icon">⚠️</span>
			<span>{error}</span>
			<button class="retry-btn" onclick={loadData}>Retry</button>
		</div>
	{/if}

	<div class="dashboard-grid">
		<!-- Left column: Real-time monitoring -->
		<div class="monitoring-section">
			<BarkGauge />

			<Card title="Audio Waveform">
				<WaveformVisualizer width={400} height={120} />
			</Card>

			<Card title="Bark Particles">
				<ParticleSystem width={400} height={200} />
			</Card>
		</div>

		<!-- Right column: Stats and recent activity -->
		<div class="stats-section">
			<RecentBarks />

			<!-- Quick Stats -->
			<div class="quick-stats">
				<div class="stat-card">
					<span class="stat-value">{dogs.length}</span>
					<span class="stat-label">Dogs</span>
				</div>
				<div class="stat-card">
					<span class="stat-value">{formatNumber(fingerprintStats?.total ?? 0)}</span>
					<span class="stat-label">Total Barks</span>
				</div>
				<div class="stat-card">
					<span class="stat-value">{formatNumber(fingerprintStats?.untagged ?? 0)}</span>
					<span class="stat-label">Untagged</span>
				</div>
				<div class="stat-card">
					<span class="stat-value">{evidenceStats ? formatDuration(evidenceStats.total_duration_seconds) : '--'}</span>
					<span class="stat-label">Evidence</span>
				</div>
			</div>

			<!-- Dog Overview -->
			{#if dogs.length > 0}
				<Card title="Dogs Overview">
					<div class="dog-grid">
						{#each dogs as dog (dog.id)}
							<a href="/dogs" class="dog-card">
								<span class="dog-emoji">{dog.emoji || '🐕'}</span>
								<span class="dog-name">{dog.name}</span>
								<span class="dog-barks">{formatNumber(dog.bark_count)} barks</span>
							</a>
						{/each}
					</div>
				</Card>
			{/if}
		</div>
	</div>
</div>

<style>
	.dashboard {
		display: flex;
		flex-direction: column;
		gap: var(--space-lg);
	}

	.dashboard-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
	}

	.title-section {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}

	.page-title {
		font-size: 1.75rem;
		font-weight: 700;
		color: var(--text-primary);
		margin: 0;
	}

	.page-subtitle {
		font-size: 0.875rem;
		color: var(--text-muted);
		margin: 0;
	}

	.connection-status {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-sm) var(--space-md);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
	}

	.connection-status .status-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--accent-coral);
	}

	.connection-status.connected .status-dot {
		background: var(--status-success);
		box-shadow: 0 0 8px var(--status-success);
		animation: pulse-glow 2s ease-in-out infinite;
	}

	@keyframes pulse-glow {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.6; }
	}

	.connection-status .status-text {
		font-size: 0.75rem;
		font-weight: 600;
		letter-spacing: 0.1em;
		color: var(--text-secondary);
	}

	.connection-status.connected .status-text {
		color: var(--status-success);
	}

	.error-banner {
		display: flex;
		align-items: center;
		gap: var(--space-md);
		padding: var(--space-md);
		background: rgba(248, 81, 73, 0.1);
		border: 1px solid var(--accent-coral);
		border-radius: var(--radius-md);
	}

	.error-icon {
		font-size: 1.25rem;
	}

	.retry-btn {
		margin-left: auto;
		padding: var(--space-xs) var(--space-sm);
		background: transparent;
		border: 1px solid var(--accent-coral);
		border-radius: var(--radius-sm);
		color: var(--accent-coral);
		font-size: 0.75rem;
		font-weight: 600;
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.retry-btn:hover {
		background: var(--accent-coral);
		color: var(--bg-base);
	}

	.dashboard-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--space-lg);
	}

	.monitoring-section,
	.stats-section {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}

	.quick-stats {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: var(--space-md);
	}

	.stat-card {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-xs);
		padding: var(--space-lg);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
	}

	.stat-value {
		font-size: 1.5rem;
		font-weight: 700;
		font-family: 'JetBrains Mono', monospace;
		color: var(--accent-teal);
	}

	.stat-label {
		font-size: 0.75rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--text-muted);
	}

	.dog-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
		gap: var(--space-sm);
	}

	.dog-card {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-xs);
		padding: var(--space-md);
		background: var(--bg-overlay);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-sm);
		text-decoration: none;
		transition: all var(--transition-fast);
	}

	.dog-card:hover {
		border-color: var(--accent-amber);
		background: var(--accent-amber-dim);
	}

	.dog-emoji {
		font-size: 1.5rem;
	}

	.dog-name {
		font-weight: 600;
		color: var(--text-primary);
	}

	.dog-barks {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	@media (max-width: 1024px) {
		.dashboard-grid {
			grid-template-columns: 1fr;
		}
	}

	@media (max-width: 640px) {
		.dashboard-header {
			flex-direction: column;
			gap: var(--space-md);
		}

		.quick-stats {
			grid-template-columns: repeat(2, 1fr);
		}
	}
</style>
