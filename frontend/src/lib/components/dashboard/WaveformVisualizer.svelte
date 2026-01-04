<script lang="ts">
	import { audioHistory, audioLevel } from '$lib/stores/audio';

	interface Props {
		height?: number;
	}

	let { height = 120 }: Props = $props();

	let canvas: HTMLCanvasElement;
	let containerWidth = $state(0);
	let containerHeight = $state(0);
	let animationFrame: number | null = null;

	// Color state for hysteresis (0=blue, 1=yellow, 2=red)
	// Using an array to track per-bar color states
	let barColorStates: number[] = [];
	let indicatorColorState = 0; // 0=blue, 1=red for the right-edge indicator

	// Hysteresis thresholds - different for going up vs down
	const THRESHOLD_LOW_UP = 0.35;    // blue -> yellow
	const THRESHOLD_LOW_DOWN = 0.25;  // yellow -> blue
	const THRESHOLD_HIGH_UP = 0.65;   // yellow -> red
	const THRESHOLD_HIGH_DOWN = 0.55; // red -> yellow

	function getColorWithHysteresis(level: number, barIndex: number): string {
		const currentState = barColorStates[barIndex] ?? 0;
		let newState = currentState;

		if (currentState === 0) {
			// Currently blue - only go to yellow if above upper threshold
			if (level >= THRESHOLD_LOW_UP) newState = 1;
		} else if (currentState === 1) {
			// Currently yellow
			if (level < THRESHOLD_LOW_DOWN) newState = 0;      // drop to blue
			else if (level >= THRESHOLD_HIGH_UP) newState = 2; // rise to red
		} else {
			// Currently red - only go to yellow if below lower threshold
			if (level < THRESHOLD_HIGH_DOWN) newState = 1;
		}

		barColorStates[barIndex] = newState;

		// Return color based on state
		if (newState === 0) return 'rgba(88, 166, 255, 0.85)';
		if (newState === 1) return 'rgba(255, 180, 50, 0.9)';
		return 'rgba(248, 81, 73, 1)';
	}

	function draw() {
		if (!canvas || containerWidth === 0) return;

		const ctx = canvas.getContext('2d');
		if (!ctx) return;

		const dpr = window.devicePixelRatio || 1;
		const w = canvas.width / dpr;
		const h = canvas.height / dpr;

		// Get current audio data
		const history = $audioHistory;
		const currentLevel = $audioLevel;

		// Background - solid fill
		ctx.fillStyle = '#0d1117';
		ctx.fillRect(0, 0, w, h);

		// Draw subtle grid
		ctx.strokeStyle = 'rgba(48, 54, 61, 0.4)';
		ctx.lineWidth = 1;
		const gridLines = 4;
		for (let i = 1; i < gridLines; i++) {
			const y = (h / gridLines) * i;
			ctx.beginPath();
			ctx.setLineDash([2, 4]);
			ctx.moveTo(0, y);
			ctx.lineTo(w, y);
			ctx.stroke();
		}
		ctx.setLineDash([]);

		// Draw center line
		ctx.strokeStyle = 'rgba(88, 166, 255, 0.15)';
		ctx.lineWidth = 1;
		ctx.beginPath();
		ctx.moveTo(0, h / 2);
		ctx.lineTo(w, h / 2);
		ctx.stroke();

		// Draw waveform bars (spectrum analyzer style)
		if (history.length > 0) {
			const barCount = Math.min(64, history.length);
			const totalGap = (barCount - 1) * 2;
			const barWidth = (w - totalGap - 12) / barCount;
			const gap = 2;
			const centerY = h / 2;

			// Ensure barColorStates array is sized correctly
			if (barColorStates.length !== barCount) {
				barColorStates = new Array(barCount).fill(0);
			}

			for (let i = 0; i < barCount; i++) {
				const sampleIndex = Math.floor((i / barCount) * history.length);
				const level = history[sampleIndex] || 0;
				const barHeight = Math.max(1, level * (h * 0.42));
				const x = i * (barWidth + gap);

				// Color with hysteresis to prevent flickering
				const color = getColorWithHysteresis(level, i);

				ctx.fillStyle = color;
				ctx.fillRect(x, centerY - barHeight, barWidth, barHeight);
				ctx.fillRect(x, centerY + 1, barWidth, barHeight);
			}

			// Draw line waveform on top
			ctx.strokeStyle = `rgba(88, 166, 255, ${0.5 + currentLevel * 0.5})`;
			ctx.lineWidth = 1.5;
			ctx.beginPath();

			const step = (w - 12) / (history.length - 1);
			history.forEach((level, i) => {
				const x = i * step;
				const y = centerY - level * (h * 0.38);
				if (i === 0) {
					ctx.moveTo(x, y);
				} else {
					ctx.lineTo(x, y);
				}
			});
			ctx.stroke();

			// Mirror line
			ctx.strokeStyle = `rgba(88, 166, 255, ${0.25 + currentLevel * 0.25})`;
			ctx.beginPath();
			history.forEach((level, i) => {
				const x = i * step;
				const y = centerY + level * (h * 0.38);
				if (i === 0) {
					ctx.moveTo(x, y);
				} else {
					ctx.lineTo(x, y);
				}
			});
			ctx.stroke();
		}

		// Current level indicator on right edge with hysteresis
		const indicatorHeight = Math.max(4, currentLevel * h * 0.75);
		const indicatorY = (h - indicatorHeight) / 2;

		// Hysteresis for indicator: go red at 0.65, go blue at 0.55
		if (indicatorColorState === 0 && currentLevel >= THRESHOLD_HIGH_UP) {
			indicatorColorState = 1;
		} else if (indicatorColorState === 1 && currentLevel < THRESHOLD_HIGH_DOWN) {
			indicatorColorState = 0;
		}
		ctx.fillStyle = indicatorColorState === 1 ? 'rgba(248, 81, 73, 1)' : 'rgba(88, 166, 255, 0.9)';
		ctx.fillRect(w - 6, indicatorY, 4, indicatorHeight);

		animationFrame = requestAnimationFrame(draw);
	}

	// Setup canvas when dimensions change (Svelte 5 idiomatic with bind:clientWidth)
	$effect(() => {
		if (canvas && containerWidth > 0) {
			const dpr = window.devicePixelRatio || 1;
			canvas.width = containerWidth * dpr;
			canvas.height = height * dpr;

			const ctx = canvas.getContext('2d');
			if (ctx) {
				ctx.scale(dpr, dpr);
			}
		}
	});

	// Animation loop with proper cleanup
	$effect(() => {
		if (canvas && containerWidth > 0) {
			animationFrame = requestAnimationFrame(draw);

			return () => {
				if (animationFrame) {
					cancelAnimationFrame(animationFrame);
					animationFrame = null;
				}
			};
		}
	});
</script>

<div class="waveform-container" bind:clientWidth={containerWidth} bind:clientHeight={containerHeight}>
	<canvas bind:this={canvas} style="width: 100%; height: {height}px"></canvas>
	<div class="waveform-label">
		<span>WAVEFORM</span>
	</div>
</div>

<style>
	.waveform-container {
		position: relative;
		width: 100%;
		height: auto;
		background: #0d1117;
		border-radius: var(--radius-md);
		overflow: hidden;
	}

	canvas {
		display: block;
		width: 100%;
	}

	.waveform-label {
		position: absolute;
		top: var(--space-xs);
		left: var(--space-sm);
		pointer-events: none;
	}

	.waveform-label span {
		font-size: 0.6rem;
		font-weight: 600;
		letter-spacing: 0.15em;
		text-transform: uppercase;
		color: var(--text-muted);
		opacity: 0.5;
	}
</style>
