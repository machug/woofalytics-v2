<script lang="ts">
	import { isDetecting, lastBark, sessionBarkCount } from '$lib/stores/bark';
	import type { Dog, FingerprintStats } from '$lib/api/types';

	interface Props {
		fingerprintStats: FingerprintStats | null;
		dogs: Dog[];
	}

	let { fingerprintStats = null, dogs = [] }: Props = $props();

	let detecting = $derived($isDetecting);
	let sessionCount = $derived($sessionBarkCount);
	let recentBark = $derived($lastBark);

	let taggedCount = $derived(fingerprintStats?.tagged ?? 0);
	let untaggedCount = $derived(fingerprintStats?.untagged ?? 0);
	let totalCount = $derived(fingerprintStats?.total ?? 0);

	let autoAssignRate = $derived(totalCount > 0 ? Math.round((taggedCount / totalCount) * 100) : 0);
	let unassignedRate = $derived(
		totalCount > 0 ? Math.round((untaggedCount / totalCount) * 100) : 0
	);

	function formatTime(date: Date | null): string {
		if (!date) return '--:--:--';
		return date.toLocaleTimeString('en-US', {
			hour12: false,
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit'
		});
	}

	function formatNumber(value: number | null | undefined): string {
		if (typeof value !== 'number') return '--';
		return value.toLocaleString();
	}

	function countNewDogs(list: Dog[]): number {
		const now = Date.now();
		const dayMs = 24 * 60 * 60 * 1000;
		return list.filter((dog) => now - new Date(dog.created_at).getTime() < dayMs).length;
	}

	let unconfirmedDogs = $derived(dogs.filter((dog) => !dog.is_confirmed).length);
	let newDogs = $derived(countNewDogs(dogs));
</script>

<div class="bark-tracker">
	<div class="tracker-header">
		<div class="status-indicator" class:active={detecting}>
			<span class="status-dot"></span>
			<div class="status-text">
				<span class="status-label">{detecting ? 'DETECTING' : 'IDLE'}</span>
				<span class="status-subtext">
					{recentBark ? `Last bark ${formatTime(recentBark.timestamp)}` : 'No barks yet'}
				</span>
			</div>
		</div>
		<div class="session-metric">
			<span class="metric-value">{sessionCount}</span>
			<span class="metric-label">Barks this session</span>
		</div>
	</div>

	<div class="metric-grid">
		<div class="metric-card">
			<span class="metric-label">Auto-assigned barks</span>
			<span class="metric-value">{fingerprintStats ? formatNumber(taggedCount) : '--'}</span>
			<span class="metric-subtext">
				{fingerprintStats ? `${autoAssignRate}% of total` : 'Loading'}
			</span>
		</div>
		<div class="metric-card">
			<span class="metric-label">Unassigned barks</span>
			<span class="metric-value">{fingerprintStats ? formatNumber(untaggedCount) : '--'}</span>
			<span class="metric-subtext">
				{fingerprintStats ? `${unassignedRate}% of total` : 'Loading'}
			</span>
		</div>
		<div class="metric-card">
			<span class="metric-label">New dog alerts (24h)</span>
			<span class="metric-value">{formatNumber(newDogs)}</span>
			<span class="metric-subtext">{formatNumber(unconfirmedDogs)} unconfirmed</span>
		</div>
		<div class="metric-card">
			<span class="metric-label">Total barks</span>
			<span class="metric-value">{fingerprintStats ? formatNumber(totalCount) : '--'}</span>
			<span class="metric-subtext">
				{fingerprintStats ? `${formatNumber(taggedCount)} tagged` : 'Loading'}
			</span>
		</div>
	</div>
</div>

<style>
	.bark-tracker {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}

	.tracker-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: var(--space-md);
		padding-bottom: var(--space-sm);
		border-bottom: 1px solid var(--border-subtle);
	}

	.status-indicator {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
	}

	.status-dot {
		width: 10px;
		height: 10px;
		border-radius: 50%;
		background: var(--text-muted);
	}

	.status-indicator.active .status-dot {
		background: var(--status-success);
		box-shadow: 0 0 10px var(--status-success);
	}

	.status-text {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.status-label {
		font-size: 0.75rem;
		font-weight: 600;
		letter-spacing: 0.1em;
		color: var(--text-secondary);
	}

	.status-indicator.active .status-label {
		color: var(--status-success);
	}

	.status-subtext {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.session-metric {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: 2px;
	}

	.metric-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: var(--space-md);
	}

	.metric-card {
		display: flex;
		flex-direction: column;
		gap: 4px;
		padding: var(--space-sm) var(--space-md);
		background: var(--bg-overlay);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-sm);
	}

	.metric-label {
		font-size: 0.65rem;
		font-weight: 600;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.metric-value {
		font-size: 1.2rem;
		font-weight: 700;
		font-family: 'JetBrains Mono', monospace;
		color: var(--text-primary);
	}

	.metric-subtext {
		font-size: 0.75rem;
		color: var(--text-secondary);
	}

	@media (max-width: 700px) {
		.tracker-header {
			flex-direction: column;
			align-items: flex-start;
		}

		.session-metric {
			align-items: flex-start;
		}

		.metric-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
