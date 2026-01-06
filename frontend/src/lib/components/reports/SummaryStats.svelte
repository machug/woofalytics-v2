<script lang="ts">
	/**
	 * SummaryStats - Display bark statistics summary cards
	 * Shows total barks, events, duration, and confidence
	 */

	interface SummaryData {
		total_barks: number;
		total_events: number;
		total_duration_seconds: number;
		avg_confidence: number;
		peak_hour: number | null;
	}

	interface Props {
		data: SummaryData | null;
		loading?: boolean;
	}

	let { data, loading = false }: Props = $props();

	// Format duration as hours:minutes:seconds
	function formatDuration(seconds: number): string {
		const hrs = Math.floor(seconds / 3600);
		const mins = Math.floor((seconds % 3600) / 60);
		const secs = Math.round(seconds % 60);

		if (hrs > 0) {
			return `${hrs}h ${mins}m ${secs}s`;
		} else if (mins > 0) {
			return `${mins}m ${secs}s`;
		}
		return `${secs}s`;
	}

	// Format hour as 12-hour time
	function formatPeakHour(hour: number | null): string {
		if (hour === null) return '—';
		const suffix = hour >= 12 ? 'PM' : 'AM';
		const displayHour = hour % 12 || 12;
		return `${displayHour}:00 ${suffix}`;
	}

	// Format confidence as percentage
	function formatConfidence(conf: number): string {
		return `${Math.round(conf * 100)}%`;
	}

	const stats = $derived([
		{
			label: 'Total Barks',
			value: data?.total_barks.toLocaleString() ?? '—',
			icon: '🔊',
			color: 'teal'
		},
		{
			label: 'Bark Events',
			value: data?.total_events.toLocaleString() ?? '—',
			icon: '📊',
			color: 'amber'
		},
		{
			label: 'Total Duration',
			value: data ? formatDuration(data.total_duration_seconds) : '—',
			icon: '⏱️',
			color: 'purple'
		},
		{
			label: 'Avg Confidence',
			value: data ? formatConfidence(data.avg_confidence) : '—',
			icon: '🎯',
			color: 'green'
		},
		{
			label: 'Peak Hour',
			value: data ? formatPeakHour(data.peak_hour) : '—',
			icon: '📈',
			color: 'red'
		}
	]);
</script>

<div class="summary-stats">
	{#each stats as stat (stat.label)}
		<div class="stat-card stat-card--{stat.color}" class:loading>
			<div class="stat-icon">{stat.icon}</div>
			<div class="stat-content">
				<span class="stat-value">{stat.value}</span>
				<span class="stat-label">{stat.label}</span>
			</div>
		</div>
	{/each}
</div>

<style>
	.summary-stats {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
		gap: var(--space-md);
	}

	.stat-card {
		display: flex;
		align-items: center;
		gap: var(--space-md);
		padding: var(--space-lg);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
		transition: all var(--transition-fast);
	}

	.stat-card:hover {
		border-color: var(--border-muted);
		transform: translateY(-2px);
	}

	.stat-card.loading {
		opacity: 0.6;
		animation: pulse 1.5s infinite;
	}

	@keyframes pulse {
		0%,
		100% {
			opacity: 0.6;
		}
		50% {
			opacity: 0.3;
		}
	}

	.stat-card--teal {
		border-left: 3px solid var(--accent-teal);
	}

	.stat-card--amber {
		border-left: 3px solid var(--accent-amber);
	}

	.stat-card--purple {
		border-left: 3px solid #a78bfa;
	}

	.stat-card--green {
		border-left: 3px solid #4ade80;
	}

	.stat-card--red {
		border-left: 3px solid #f87171;
	}

	.stat-icon {
		font-size: 1.5rem;
	}

	.stat-content {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}

	.stat-value {
		font-size: 1.25rem;
		font-weight: 700;
		font-family: 'JetBrains Mono', monospace;
		color: var(--text-primary);
	}

	.stat-label {
		font-size: 0.7rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	@media (max-width: 640px) {
		.summary-stats {
			grid-template-columns: repeat(2, 1fr);
		}

		.stat-card {
			padding: var(--space-md);
		}

		.stat-icon {
			font-size: 1.25rem;
		}

		.stat-value {
			font-size: 1rem;
		}
	}
</style>
