<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		pipelineStore,
		vadState,
		yamnetState,
		clapState,
		pipelineStats,
		pipelineConnected
	} from '$lib/stores/pipeline';

	let vad = $derived($vadState);
	let yamnet = $derived($yamnetState);
	let clap = $derived($clapState);
	let stats = $derived($pipelineStats);
	let connected = $derived($pipelineConnected);

	onMount(() => {
		pipelineStore.connect();
	});

	onDestroy(() => {
		pipelineStore.disconnect();
	});

	function formatDb(db: number | undefined | null): string {
		if (db === undefined || db === null || !isFinite(db)) return '--';
		return `${db.toFixed(1)} dB`;
	}

	function formatPercent(value: number | undefined | null): string {
		if (value === undefined || value === null) return '--';
		return `${(value * 100).toFixed(1)}%`;
	}
</script>

<div class="pipeline-monitor">
	<div class="pipeline-header">
		<span class="title">Detection Pipeline</span>
		<span class="connection-status" class:connected>
			{connected ? 'LIVE' : 'OFFLINE'}
		</span>
	</div>

	<div class="pipeline-stages">
		<!-- VAD Stage -->
		<div class="stage" class:active={vad?.passed} class:rejected={vad && !vad.passed}>
			<div class="stage-header">
				<span class="stage-name">VAD</span>
				<span class="stage-status" style="color: {vad?.passed ? 'var(--status-success)' : 'var(--text-muted)'}">
					{vad?.passed ? 'PASS' : 'SKIP'}
				</span>
			</div>
			<div class="stage-meter">
				<div class="meter-bar-container">
					<div
						class="meter-bar vad"
						style="width: {vad ? Math.max(0, Math.min(100, ((vad.level_db + 60) / 60) * 100)) : 0}%"
					></div>
					<div
						class="threshold-marker"
						style="left: {vad ? Math.max(0, Math.min(100, ((vad.threshold_db + 60) / 60) * 100)) : 33}%"
					></div>
				</div>
				<span class="meter-value">{formatDb(vad?.level_db)}</span>
			</div>
		</div>

		<!-- Arrow -->
		<div class="arrow">→</div>

		<!-- YAMNet Stage -->
		<div class="stage" class:active={yamnet?.passed} class:rejected={yamnet && !yamnet.passed}>
			<div class="stage-header">
				<span class="stage-name">YAMNet</span>
				<span class="stage-status" style="color: {yamnet?.passed ? 'var(--status-success)' : 'var(--accent-teal)'}">
					{yamnet?.passed ? 'DOG' : 'SKIP'}
				</span>
			</div>
			<div class="stage-meter">
				<div class="meter-bar-container">
					<div
						class="meter-bar yamnet"
						style="width: {yamnet ? yamnet.dog_probability * 100 : 0}%"
					></div>
					<div
						class="threshold-marker"
						style="left: {yamnet ? yamnet.threshold * 100 : 5}%"
					></div>
				</div>
				<span class="meter-value">{formatPercent(yamnet?.dog_probability)}</span>
			</div>
		</div>

		<!-- Arrow -->
		<div class="arrow">→</div>

		<!-- CLAP Stage -->
		<div class="stage" class:active={clap?.is_barking} class:rejected={clap && !clap.is_barking}>
			<div class="stage-header">
				<span class="stage-name">CLAP</span>
				<span class="stage-status" style="color: {clap?.is_barking ? 'var(--status-success)' : 'var(--accent-amber)'}">
					{clap?.is_barking ? 'BARK!' : 'NO'}
				</span>
			</div>
			<div class="stage-meter">
				<div class="meter-bar-container">
					<div
						class="meter-bar clap"
						class:barking={clap?.is_barking}
						style="width: {clap ? clap.probability * 100 : 0}%"
					></div>
					<div
						class="threshold-marker"
						style="left: {clap ? clap.threshold * 100 : 70}%"
					></div>
				</div>
				<span class="meter-value">{formatPercent(clap?.probability)}</span>
			</div>
			<div class="clap-label">
				{clap?.top_label ?? '--'}
			</div>
		</div>
	</div>

	<div class="pipeline-stats">
		<div class="stat">
			<span class="stat-label">VAD Skip</span>
			<span class="stat-value">{stats?.vad_skipped ?? 0}</span>
		</div>
		<div class="stat">
			<span class="stat-label">YAMNet Skip</span>
			<span class="stat-value">{stats?.yamnet_skipped ?? 0}</span>
		</div>
		<div class="stat">
			<span class="stat-label">CLAP Runs</span>
			<span class="stat-value">{stats?.clap_inferences ?? 0}</span>
		</div>
		<div class="stat highlight">
			<span class="stat-label">Barks</span>
			<span class="stat-value">{stats?.total_barks ?? 0}</span>
		</div>
	</div>
</div>

<style>
	.pipeline-monitor {
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
		padding: var(--space-md);
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}

	.pipeline-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.title {
		font-size: 0.75rem;
		font-weight: 600;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--text-secondary);
	}

	.connection-status {
		font-size: 0.65rem;
		font-weight: 600;
		letter-spacing: 0.1em;
		padding: 2px 6px;
		border-radius: var(--radius-sm);
		background: var(--bg-overlay);
		color: var(--text-muted);
	}

	.connection-status.connected {
		background: var(--status-success);
		color: var(--bg-base);
	}

	.pipeline-stages {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
	}

	.stage {
		flex: 1;
		background: var(--bg-overlay);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-sm);
		padding: var(--space-sm);
		transition: all 0.15s ease;
	}

	.stage.active {
		border-color: var(--status-success);
		box-shadow: 0 0 8px rgba(34, 197, 94, 0.2);
	}

	.stage.rejected {
		opacity: 0.6;
	}

	.stage-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: var(--space-xs);
	}

	.stage-name {
		font-size: 0.7rem;
		font-weight: 600;
		letter-spacing: 0.08em;
		color: var(--text-secondary);
	}

	.stage-status {
		font-size: 0.65rem;
		font-weight: 700;
		font-family: 'JetBrains Mono', monospace;
	}

	.stage-meter {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
	}

	.meter-bar-container {
		flex: 1;
		height: 8px;
		background: var(--bg-base);
		border-radius: 4px;
		position: relative;
		overflow: visible;
	}

	.meter-bar {
		height: 100%;
		border-radius: 4px;
		transition: width 0.1s ease;
	}

	.meter-bar.vad {
		background: linear-gradient(90deg, var(--accent-teal-dim), var(--accent-teal));
	}

	.meter-bar.yamnet {
		background: linear-gradient(90deg, var(--accent-amber-dim), var(--accent-amber));
	}

	.meter-bar.clap {
		background: linear-gradient(90deg, var(--accent-coral-dim), var(--accent-coral));
	}

	.meter-bar.clap.barking {
		background: var(--status-success);
		animation: pulse 0.5s ease infinite;
	}

	@keyframes pulse {
		0%,
		100% {
			opacity: 1;
		}
		50% {
			opacity: 0.7;
		}
	}

	.threshold-marker {
		position: absolute;
		top: -2px;
		bottom: -2px;
		width: 2px;
		background: var(--text-primary);
		border-radius: 1px;
	}

	.meter-value {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.65rem;
		color: var(--text-muted);
		min-width: 45px;
		text-align: right;
	}

	.clap-label {
		font-size: 0.6rem;
		color: var(--text-muted);
		margin-top: 2px;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.arrow {
		font-size: 1rem;
		color: var(--text-muted);
		flex-shrink: 0;
	}

	.pipeline-stats {
		display: flex;
		justify-content: space-between;
		padding-top: var(--space-sm);
		border-top: 1px solid var(--border-subtle);
	}

	.stat {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2px;
	}

	.stat-label {
		font-size: 0.6rem;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.stat-value {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.85rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.stat.highlight .stat-value {
		color: var(--accent-amber);
	}

	@media (max-width: 600px) {
		.pipeline-stages {
			flex-direction: column;
		}

		.arrow {
			transform: rotate(90deg);
		}

		.stage {
			width: 100%;
		}
	}
</style>
