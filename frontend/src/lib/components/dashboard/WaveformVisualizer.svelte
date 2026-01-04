<script lang="ts">
	import { onMount } from 'svelte';
	import { audioHistory, audioLevel } from '$lib/stores/audio';

	interface Props {
		width?: number;
		height?: number;
	}

	let { width = 400, height = 150 }: Props = $props();

	let canvas: HTMLCanvasElement;
	let ctx: CanvasRenderingContext2D | null = null;
	let animationFrame: number;

	// Phosphor persistence buffers for glow effect
	let previousFrames: ImageData[] = [];
	const PERSISTENCE_FRAMES = 5;
	const PERSISTENCE_DECAY = 0.7;

	// Color interpolation based on amplitude
	function getWaveformColor(amplitude: number): string {
		// Interpolate from teal (low) -> amber (medium) -> coral (high)
		if (amplitude < 0.4) {
			// Teal range
			const t = amplitude / 0.4;
			return `rgba(88, 166, 255, ${0.6 + t * 0.4})`;
		} else if (amplitude < 0.7) {
			// Teal to amber transition
			const t = (amplitude - 0.4) / 0.3;
			const r = Math.round(88 + (255 - 88) * t);
			const g = Math.round(166 + (180 - 166) * t);
			const b = Math.round(255 - 255 * t);
			return `rgba(${r}, ${g}, ${b}, 1)`;
		} else {
			// Amber to coral (high amplitude / near clipping)
			const t = (amplitude - 0.7) / 0.3;
			const r = 255;
			const g = Math.round(180 - 100 * t);
			const b = Math.round(0 + 73 * t);
			return `rgba(${r}, ${g}, ${b}, 1)`;
		}
	}

	function draw() {
		if (!ctx || !canvas) return;

		const dpr = window.devicePixelRatio || 1;
		const w = canvas.width / dpr;
		const h = canvas.height / dpr;

		// Store previous frame for persistence effect
		if (previousFrames.length >= PERSISTENCE_FRAMES) {
			previousFrames.shift();
		}
		try {
			previousFrames.push(ctx.getImageData(0, 0, canvas.width, canvas.height));
		} catch {
			// Canvas may not be ready
		}

		// Clear with slight opacity for trail effect
		ctx.fillStyle = 'rgba(13, 17, 23, 0.3)';
		ctx.fillRect(0, 0, w, h);

		// Draw persistence frames (phosphor glow)
		ctx.save();
		previousFrames.forEach((frame, index) => {
			const alpha = ((index + 1) / PERSISTENCE_FRAMES) * PERSISTENCE_DECAY * 0.3;
			ctx!.globalAlpha = alpha;
			try {
				ctx!.putImageData(frame, 0, 0);
			} catch {
				// Ignore errors
			}
		});
		ctx.restore();

		// Get current audio history
		const history = $audioHistory;
		const currentLevel = $audioLevel;

		// Draw grid lines (subtle)
		ctx.strokeStyle = 'rgba(48, 54, 61, 0.5)';
		ctx.lineWidth = 1;
		for (let i = 0; i <= 4; i++) {
			const y = (h / 4) * i;
			ctx.beginPath();
			ctx.moveTo(0, y);
			ctx.lineTo(w, y);
			ctx.stroke();
		}

		// Draw center line
		ctx.strokeStyle = 'rgba(88, 166, 255, 0.3)';
		ctx.beginPath();
		ctx.moveTo(0, h / 2);
		ctx.lineTo(w, h / 2);
		ctx.stroke();

		// Draw waveform
		if (history.length > 0) {
			const step = w / (history.length - 1);
			const centerY = h / 2;

			// Glow layer
			ctx.save();
			ctx.shadowColor = getWaveformColor(currentLevel);
			ctx.shadowBlur = 15;
			ctx.strokeStyle = getWaveformColor(currentLevel);
			ctx.lineWidth = 2;
			ctx.lineCap = 'round';
			ctx.lineJoin = 'round';

			ctx.beginPath();
			history.forEach((level, i) => {
				const x = i * step;
				const amplitude = level * (h * 0.4);
				// Create oscillating wave effect
				const y = centerY + Math.sin(i * 0.3 + Date.now() * 0.002) * amplitude;

				if (i === 0) {
					ctx!.moveTo(x, y);
				} else {
					ctx!.lineTo(x, y);
				}
			});
			ctx.stroke();
			ctx.restore();

			// Sharp line on top
			ctx.strokeStyle = getWaveformColor(currentLevel);
			ctx.lineWidth = 1.5;
			ctx.beginPath();
			history.forEach((level, i) => {
				const x = i * step;
				const amplitude = level * (h * 0.4);
				const y = centerY + Math.sin(i * 0.3 + Date.now() * 0.002) * amplitude;

				if (i === 0) {
					ctx!.moveTo(x, y);
				} else {
					ctx!.lineTo(x, y);
				}
			});
			ctx.stroke();

			// Mirror wave (subtle)
			ctx.globalAlpha = 0.3;
			ctx.beginPath();
			history.forEach((level, i) => {
				const x = i * step;
				const amplitude = level * (h * 0.4);
				const y = centerY - Math.sin(i * 0.3 + Date.now() * 0.002) * amplitude;

				if (i === 0) {
					ctx!.moveTo(x, y);
				} else {
					ctx!.lineTo(x, y);
				}
			});
			ctx.stroke();
			ctx.globalAlpha = 1;
		}

		animationFrame = requestAnimationFrame(draw);
	}

	function setupCanvas() {
		if (!canvas) return;

		const dpr = window.devicePixelRatio || 1;
		canvas.width = width * dpr;
		canvas.height = height * dpr;

		ctx = canvas.getContext('2d');
		if (ctx) {
			ctx.scale(dpr, dpr);
		}
	}

	onMount(() => {
		setupCanvas();
		animationFrame = requestAnimationFrame(draw);

		return () => {
			if (animationFrame) {
				cancelAnimationFrame(animationFrame);
			}
		};
	});

	$effect(() => {
		// Re-setup canvas if dimensions change
		if (width || height) {
			setupCanvas();
		}
	});
</script>

<div class="waveform-container">
	<canvas bind:this={canvas} style="width: {width}px; height: {height}px"></canvas>
	<div class="waveform-overlay">
		<span class="label">AUDIO WAVEFORM</span>
	</div>
</div>

<style>
	.waveform-container {
		position: relative;
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
		overflow: hidden;
	}

	canvas {
		display: block;
	}

	.waveform-overlay {
		position: absolute;
		top: var(--space-sm);
		left: var(--space-sm);
		pointer-events: none;
	}

	.label {
		font-size: 0.65rem;
		font-weight: 600;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--text-muted);
		background: rgba(13, 17, 23, 0.7);
		padding: 2px 6px;
		border-radius: var(--radius-sm);
	}
</style>
