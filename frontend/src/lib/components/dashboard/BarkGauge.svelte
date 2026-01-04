<script lang="ts">
	import { audioLevel, audioPeak, isClipping } from '$lib/stores/audio';
	import { isDetecting, sessionBarkCount, lastBark, type BarkEvent } from '$lib/stores/bark';

	// Derived display values
	let displayLevel = $derived(Math.round($audioLevel * 100));
	let displayPeak = $derived(Math.round($audioPeak * 100));
	let detecting = $derived($isDetecting);
	let clipping = $derived($isClipping);
	let barkCount = $derived($sessionBarkCount);
	let recentBark = $derived($lastBark);

	// Format timestamp for display
	function formatTime(date: Date | null): string {
		if (!date) return '--:--:--';
		return date.toLocaleTimeString('en-US', {
			hour12: false,
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit'
		});
	}

	// Get level class for styling
	function getLevelClass(level: number): string {
		if (level > 90) return 'critical';
		if (level > 70) return 'high';
		if (level > 40) return 'medium';
		return 'low';
	}
</script>

<div class="bark-gauge">
	<div class="gauge-header">
		<div class="status-indicator" class:active={detecting}>
			<span class="status-dot"></span>
			<span class="status-text">{detecting ? 'DETECTING' : 'IDLE'}</span>
		</div>
		<div class="bark-counter">
			<span class="counter-value">{barkCount}</span>
			<span class="counter-label">BARKS</span>
		</div>
	</div>

	<div class="level-display">
		<div class="level-bar-container">
			<div class="level-bar {getLevelClass(displayLevel)}" style="width: {displayLevel}%"></div>
			<div class="peak-marker" style="left: {displayPeak}%"></div>
		</div>
		<div class="level-value" class:clipping>
			{displayLevel}%
			{#if clipping}
				<span class="clip-warning">CLIP</span>
			{/if}
		</div>
	</div>

	<div class="telemetry-readouts">
		<div class="readout">
			<span class="readout-label">PEAK</span>
			<span class="readout-value">{displayPeak}%</span>
		</div>
		<div class="readout">
			<span class="readout-label">LAST BARK</span>
			<span class="readout-value">{formatTime(recentBark?.timestamp ?? null)}</span>
		</div>
		<div class="readout">
			<span class="readout-label">CONFIDENCE</span>
			<span class="readout-value"
				>{recentBark ? Math.round(recentBark.confidence * 100) + '%' : '--'}</span
			>
		</div>
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
	}

	.gauge-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
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
		transition: all var(--transition-base);
	}

	.status-indicator.active .status-dot {
		background: var(--status-success);
		box-shadow: 0 0 10px var(--status-success);
		animation: pulse-glow 1.5s ease-in-out infinite;
	}

	@keyframes pulse-glow {
		0%,
		100% {
			opacity: 1;
			transform: scale(1);
		}
		50% {
			opacity: 0.7;
			transform: scale(1.2);
		}
	}

	.status-text {
		font-size: 0.75rem;
		font-weight: 600;
		letter-spacing: 0.1em;
		color: var(--text-secondary);
	}

	.status-indicator.active .status-text {
		color: var(--status-success);
	}

	.bark-counter {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
	}

	.counter-value {
		font-size: 2rem;
		font-weight: 700;
		font-family: 'JetBrains Mono', monospace;
		color: var(--accent-amber);
		line-height: 1;
	}

	.counter-label {
		font-size: 0.65rem;
		font-weight: 600;
		letter-spacing: 0.15em;
		color: var(--text-muted);
	}

	.level-display {
		display: flex;
		align-items: center;
		gap: var(--space-md);
	}

	.level-bar-container {
		flex: 1;
		height: 24px;
		background: var(--bg-overlay);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		position: relative;
		overflow: hidden;
	}

	.level-bar {
		height: 100%;
		transition: width 0.05s linear;
		border-radius: var(--radius-sm);
	}

	.level-bar.low {
		background: linear-gradient(90deg, var(--accent-teal-dim), var(--accent-teal));
	}

	.level-bar.medium {
		background: linear-gradient(90deg, var(--accent-teal), var(--accent-amber));
	}

	.level-bar.high {
		background: linear-gradient(90deg, var(--accent-amber), var(--accent-coral));
	}

	.level-bar.critical {
		background: var(--accent-coral);
		animation: critical-flash 0.3s ease-in-out infinite alternate;
	}

	@keyframes critical-flash {
		from {
			opacity: 0.8;
		}
		to {
			opacity: 1;
		}
	}

	.peak-marker {
		position: absolute;
		top: 0;
		bottom: 0;
		width: 2px;
		background: var(--text-primary);
		transition: left 0.1s ease-out;
	}

	.level-value {
		font-family: 'JetBrains Mono', monospace;
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--text-primary);
		min-width: 80px;
		text-align: right;
		display: flex;
		align-items: center;
		gap: var(--space-xs);
	}

	.level-value.clipping {
		color: var(--accent-coral);
	}

	.clip-warning {
		font-size: 0.65rem;
		background: var(--accent-coral);
		color: var(--bg-base);
		padding: 2px 4px;
		border-radius: var(--radius-sm);
		animation: blink 0.5s ease-in-out infinite;
	}

	@keyframes blink {
		0%,
		100% {
			opacity: 1;
		}
		50% {
			opacity: 0.5;
		}
	}

	.telemetry-readouts {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: var(--space-md);
		padding-top: var(--space-sm);
		border-top: 1px solid var(--border-subtle);
	}

	.readout {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.readout-label {
		font-size: 0.65rem;
		font-weight: 600;
		letter-spacing: 0.1em;
		color: var(--text-muted);
	}

	.readout-value {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.875rem;
		color: var(--text-secondary);
	}

	.attribution {
		display: flex;
		align-items: center;
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
