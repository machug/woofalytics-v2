<script lang="ts">
	import { recentFingerprints, fingerprintsLoading, type Fingerprint } from '$lib/stores/fingerprints';
	import { formatTime } from '$lib/utils/format';

	// Get recent fingerprints (already limited to 5)
	let fingerprints = $derived($recentFingerprints);
	let loading = $derived($fingerprintsLoading);

	function formatConfidence(confidence: number): string {
		return Math.round(confidence * 100) + '%';
	}

	function getConfidenceClass(confidence: number): string {
		if (confidence >= 0.8) return 'high';
		if (confidence >= 0.5) return 'medium';
		return 'low';
	}

	// Get display confidence (prefer match_confidence, fallback to detection_probability)
	function getConfidence(fp: Fingerprint): number {
		return fp.match_confidence ?? fp.detection_probability ?? 0;
	}
</script>

<div class="recent-barks">
	<div class="header">
		<h3 class="title">Recent Detections</h3>
		<span class="count">{fingerprints.length} shown</span>
	</div>

	{#if loading}
		<div class="empty-state">
			<span class="text">Loading...</span>
		</div>
	{:else if fingerprints.length === 0}
		<div class="empty-state">
			<span class="emoji">🔇</span>
			<span class="text">No barks detected yet</span>
		</div>
	{:else}
		<div class="bark-list">
			{#each fingerprints as fp (fp.id)}
				<div class="bark-item" class:new={Date.now() - fp.timestamp.getTime() < 3000}>
					<div class="bark-time">{formatTime(fp.timestamp)}</div>
					<div class="bark-details">
						{#if fp.dog_name}
							<span class="dog-name">{fp.dog_name}</span>
						{:else}
							<span class="untagged">Untagged</span>
						{/if}
						<span class="confidence {getConfidenceClass(getConfidence(fp))}">
							{formatConfidence(getConfidence(fp))}
						</span>
					</div>
					{#if fp.duration_ms}
						<div class="bark-duration">{Math.round(fp.duration_ms)}ms</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.recent-barks {
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
		padding: var(--space-lg);
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
		max-height: 400px;
		overflow: hidden;
	}

	.header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.title {
		font-size: 0.875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-primary);
		margin: 0;
	}

	.count {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.empty-state {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--space-sm);
		padding: var(--space-xl);
	}

	.empty-state .emoji {
		font-size: 2rem;
		opacity: 0.5;
	}

	.empty-state .text {
		font-size: 0.875rem;
		color: var(--text-muted);
	}

	.bark-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
		overflow-y: auto;
	}

	.bark-item {
		display: grid;
		grid-template-columns: auto 1fr auto;
		gap: var(--space-md);
		align-items: center;
		padding: var(--space-sm) var(--space-md);
		background: var(--bg-overlay);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-sm);
		transition: all var(--transition-fast);
	}

	.bark-item.new {
		border-color: var(--accent-amber);
		background: var(--accent-amber-dim);
		animation: flash-new 0.5s ease-out;
	}

	@keyframes flash-new {
		from {
			background: var(--accent-amber);
			transform: scale(1.02);
		}
		to {
			background: var(--accent-amber-dim);
			transform: scale(1);
		}
	}

	.bark-time {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.bark-details {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
	}

	.dog-name {
		font-weight: 600;
		color: var(--text-primary);
	}

	.untagged {
		font-style: italic;
		color: var(--text-muted);
	}

	.confidence {
		font-size: 0.75rem;
		font-family: 'JetBrains Mono', monospace;
		padding: 2px 6px;
		border-radius: var(--radius-sm);
	}

	.confidence.high {
		background: rgba(63, 185, 80, 0.2);
		color: var(--status-success);
	}

	.confidence.medium {
		background: var(--accent-amber-dim);
		color: var(--accent-amber);
	}

	.confidence.low {
		background: rgba(248, 81, 73, 0.2);
		color: var(--accent-coral);
	}

	.bark-duration {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.7rem;
		color: var(--text-muted);
	}
</style>
