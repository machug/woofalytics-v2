<script lang="ts">
	interface Props {
		degrees: number | null;
		direction: string | null;
		size?: number;
	}

	let { degrees, direction, size = 80 }: Props = $props();

	// Convert degrees to rotation (0° = front/top, clockwise)
	let rotation = $derived(degrees !== null ? degrees : 0);
	let hasData = $derived(degrees !== null);
</script>

<div class="doa-compass" style="--size: {size}px">
	<div class="compass-ring">
		<!-- Cardinal directions -->
		<span class="cardinal n">F</span>
		<span class="cardinal e">R</span>
		<span class="cardinal s">B</span>
		<span class="cardinal w">L</span>

		<!-- Compass face -->
		<div class="compass-face">
			{#if hasData}
				<!-- Direction arrow -->
				<svg
					class="arrow"
					viewBox="0 0 24 24"
					style="transform: rotate({rotation}deg)"
				>
					<path
						d="M12 2L8 10h3v10h2V10h3L12 2z"
						fill="currentColor"
					/>
				</svg>
			{:else}
				<span class="no-data">--</span>
			{/if}
		</div>
	</div>

	{#if hasData && direction}
		<div class="direction-label">
			<span class="degrees">{degrees}°</span>
			<span class="label">{direction}</span>
		</div>
	{/if}
</div>

<style>
	.doa-compass {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-xs);
	}

	.compass-ring {
		position: relative;
		width: var(--size);
		height: var(--size);
		border: 2px solid var(--border-default);
		border-radius: 50%;
		background: var(--bg-overlay);
	}

	.cardinal {
		position: absolute;
		font-size: 0.6rem;
		font-weight: 700;
		color: var(--text-muted);
		text-transform: uppercase;
	}

	.cardinal.n {
		top: 4px;
		left: 50%;
		transform: translateX(-50%);
		color: var(--accent-teal);
	}

	.cardinal.e {
		right: 4px;
		top: 50%;
		transform: translateY(-50%);
	}

	.cardinal.s {
		bottom: 4px;
		left: 50%;
		transform: translateX(-50%);
	}

	.cardinal.w {
		left: 4px;
		top: 50%;
		transform: translateY(-50%);
	}

	.compass-face {
		position: absolute;
		inset: 12px;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg-surface);
		border-radius: 50%;
		border: 1px solid var(--border-subtle);
	}

	.arrow {
		width: 60%;
		height: 60%;
		color: var(--accent-amber);
		transition: transform 0.3s ease-out;
	}

	.no-data {
		font-size: 0.875rem;
		color: var(--text-muted);
	}

	.direction-label {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2px;
	}

	.degrees {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--accent-amber);
	}

	.label {
		font-size: 0.65rem;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}
</style>
