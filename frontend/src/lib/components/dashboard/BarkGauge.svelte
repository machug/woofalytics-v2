<script lang="ts">
	import { isDetecting, sessionBarkCount, lastBark } from '$lib/stores/bark';
	import { formatTime } from '$lib/utils/format';

	// Derived display values
	let detecting = $derived($isDetecting);
	let barkCount = $derived($sessionBarkCount);
	let recentBark = $derived($lastBark);

	// Time since last bark
	function getTimeSince(date: Date | null): string {
		if (!date) return '--';
		const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
		if (seconds < 60) return `${seconds}s ago`;
		const minutes = Math.floor(seconds / 60);
		if (minutes < 60) return `${minutes}m ago`;
		const hours = Math.floor(minutes / 60);
		return `${hours}h ago`;
	}

	// Update time since every second
	let timeSinceLastBark = $state('--');
	$effect(() => {
		const bark = recentBark;
		if (!bark) {
			timeSinceLastBark = '--';
			return;
		}
		timeSinceLastBark = getTimeSince(bark.timestamp);
		const interval = setInterval(() => {
			timeSinceLastBark = getTimeSince(bark.timestamp);
		}, 1000);
		return () => clearInterval(interval);
	});
</script>

<div class="bark-gauge" class:barking={detecting}>
	<div class="gauge-header">
		<div class="status-section">
			<div class="status-indicator" class:active={detecting}>
				<span class="status-dot"></span>
				<span class="status-text">{detecting ? 'BARK!' : 'LISTENING'}</span>
			</div>
		</div>
	</div>

	<div class="bark-count-display">
		<span class="count-value">{barkCount}</span>
		<span class="count-label">barks this session</span>
	</div>

	<div class="last-bark-info">
		<div class="info-row">
			<span class="info-label">Last Detected</span>
			<span class="info-value">{formatTime(recentBark?.timestamp ?? null)}</span>
		</div>
		<div class="info-row">
			<span class="info-label">Time Ago</span>
			<span class="info-value">{timeSinceLastBark}</span>
		</div>
		{#if recentBark}
			<div class="info-row">
				<span class="info-label">Confidence</span>
				<span class="info-value confidence">{Math.round(recentBark.confidence * 100)}%</span>
			</div>
		{/if}
	</div>

	{#if recentBark?.dog_name}
		<div class="attribution">
			<span class="dog-emoji">🐕</span>
			<span class="dog-name">{recentBark.dog_name}</span>
		</div>
	{/if}
</div>

<style>
	.bark-gauge {
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
		padding: var(--space-lg);
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
		transition: all 0.2s ease;
	}

	.bark-gauge.barking {
		border-color: var(--status-success);
		box-shadow: 0 0 20px rgba(34, 197, 94, 0.3);
	}

	.gauge-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.status-section {
		display: flex;
		align-items: center;
		gap: var(--space-md);
	}

	.status-indicator {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-xs) var(--space-sm);
		background: var(--bg-overlay);
		border-radius: var(--radius-sm);
	}

	.status-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--text-muted);
		transition: all var(--transition-base);
	}

	.status-indicator.active .status-dot {
		background: var(--status-success);
		box-shadow: 0 0 10px var(--status-success);
		animation: pulse-glow 0.5s ease-in-out infinite;
	}

	@keyframes pulse-glow {
		0%,
		100% {
			opacity: 1;
			transform: scale(1);
		}
		50% {
			opacity: 0.7;
			transform: scale(1.3);
		}
	}

	.status-text {
		font-size: 0.7rem;
		font-weight: 700;
		letter-spacing: 0.1em;
		color: var(--text-muted);
	}

	.status-indicator.active .status-text {
		color: var(--status-success);
	}

	.bark-count-display {
		display: flex;
		flex-direction: column;
		align-items: center;
		padding: var(--space-lg) 0;
	}

	.count-value {
		font-size: 4rem;
		font-weight: 700;
		font-family: 'JetBrains Mono', monospace;
		color: var(--accent-amber);
		line-height: 1;
	}

	.count-label {
		font-size: 0.75rem;
		font-weight: 500;
		letter-spacing: 0.05em;
		color: var(--text-muted);
		margin-top: var(--space-xs);
	}

	.last-bark-info {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
		padding: var(--space-sm);
		background: var(--bg-overlay);
		border-radius: var(--radius-sm);
	}

	.info-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.info-label {
		font-size: 0.7rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.info-value {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.8rem;
		color: var(--text-secondary);
	}

	.info-value.confidence {
		color: var(--accent-teal);
	}

	.attribution {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-sm);
		padding: var(--space-sm);
		background: var(--accent-amber-dim);
		border: 1px solid var(--accent-amber);
		border-radius: var(--radius-sm);
	}

	.dog-emoji {
		font-size: 1.25rem;
	}

	.dog-name {
		font-weight: 600;
		color: var(--accent-amber);
	}
</style>
