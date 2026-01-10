<script lang="ts">
	import { onMount } from 'svelte';

	interface Props {
		height?: number;
	}

	let { height = 120 }: Props = $props();

	let canvas: HTMLCanvasElement;
	let containerWidth = $state(0);
	let audioContext: AudioContext | null = null;
	let analyser: AnalyserNode | null = null;
	let dataArray: Uint8Array<ArrayBuffer> | null = null;
	let animationId: number | null = null;
	let isRunning = $state(false);
	let error = $state<string | null>(null);

	// Accessibility: Check for reduced motion preference
	const prefersReducedMotion =
		typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

	async function startCapture() {
		try {
			error = null;

			// Request microphone access
			const stream = await navigator.mediaDevices.getUserMedia({
				audio: {
					echoCancellation: false,
					noiseSuppression: false,
					autoGainControl: false
				}
			});

			// Create audio context and analyser
			audioContext = new AudioContext();
			analyser = audioContext.createAnalyser();
			analyser.fftSize = 512; // 256 frequency bins
			analyser.smoothingTimeConstant = 0.3;
			// Tighter decibel range for better visual dynamic range
			analyser.minDecibels = -70;
			analyser.maxDecibels = -20;

			const source = audioContext.createMediaStreamSource(stream);
			source.connect(analyser);
			// Don't connect to destination - we don't want to play back

			dataArray = new Uint8Array(analyser.frequencyBinCount);
			isRunning = true;
			draw();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to access microphone';
			console.error('Spectrogram error:', err);
		}
	}

	function stopCapture() {
		if (animationId) {
			cancelAnimationFrame(animationId);
			animationId = null;
		}
		if (audioContext) {
			audioContext.close();
			audioContext = null;
		}
		analyser = null;
		dataArray = null;
		isRunning = false;
	}

	function draw() {
		if (!canvas || !analyser || !dataArray || !isRunning || containerWidth === 0) return;

		const ctx = canvas.getContext('2d');
		if (!ctx) return;

		// Get frequency data
		analyser.getByteFrequencyData(dataArray);

		// Accessibility: For reduced motion, show static bar visualization instead of scrolling
		if (prefersReducedMotion) {
			// Clear and draw static frequency bars
			ctx.fillStyle = '#0d1117';
			ctx.fillRect(0, 0, canvas.width, canvas.height);

			const binCount = dataArray.length;
			const barWidth = canvas.width / binCount;

			for (let i = 0; i < binCount; i++) {
				const value = dataArray[i];
				const percent = value / 255;
				const barHeight = percent * canvas.height;

				// Use same NASA Teal colormap
				let r, g, b;
				if (percent < 0.33) {
					const t = percent / 0.33;
					r = Math.floor(13 + t * 20);
					g = Math.floor(17 + t * 60);
					b = Math.floor(23 + t * 70);
				} else if (percent < 0.66) {
					const t = (percent - 0.33) / 0.33;
					r = Math.floor(33 + t * 55);
					g = Math.floor(77 + t * 89);
					b = Math.floor(93 + t * 162);
				} else {
					const t = (percent - 0.66) / 0.34;
					r = Math.floor(88 + t * 167);
					g = Math.floor(166 + t * 89);
					b = 255;
				}

				ctx.fillStyle = `rgb(${r}, ${g}, ${b})`;
				ctx.fillRect(i * barWidth, canvas.height - barHeight, barWidth - 1, barHeight);
			}

			animationId = requestAnimationFrame(draw);
			return;
		}

		// Shift existing image left by 1 pixel
		const imageData = ctx.getImageData(1, 0, canvas.width - 1, canvas.height);
		ctx.putImageData(imageData, 0, 0);

		// Draw new column on right edge
		const binCount = dataArray.length;
		const binHeight = canvas.height / binCount;

		for (let i = 0; i < binCount; i++) {
			const value = dataArray[i];
			const percent = value / 255;

			// NASA Teal colormap: dark -> deep teal -> bright cyan -> white
			let r, g, b;
			if (percent < 0.33) {
				// Dark to deep teal
				const t = percent / 0.33;
				r = Math.floor(13 + t * 20);      // 13 -> 33
				g = Math.floor(17 + t * 60);      // 17 -> 77
				b = Math.floor(23 + t * 70);      // 23 -> 93
			} else if (percent < 0.66) {
				// Deep teal to bright cyan
				const t = (percent - 0.33) / 0.33;
				r = Math.floor(33 + t * 55);      // 33 -> 88
				g = Math.floor(77 + t * 89);      // 77 -> 166
				b = Math.floor(93 + t * 162);     // 93 -> 255
			} else {
				// Bright cyan to white
				const t = (percent - 0.66) / 0.34;
				r = Math.floor(88 + t * 167);     // 88 -> 255
				g = Math.floor(166 + t * 89);     // 166 -> 255
				b = 255;                          // stays 255
			}

			ctx.fillStyle = `rgb(${r}, ${g}, ${b})`;

			// Draw from bottom (low freq) to top (high freq)
			const y = canvas.height - (i + 1) * binHeight;
			ctx.fillRect(canvas.width - 1, y, 1, Math.ceil(binHeight));
		}

		animationId = requestAnimationFrame(draw);
	}

	// Setup canvas dimensions - use CSS pixels directly, browser handles DPR scaling
	$effect(() => {
		if (canvas && containerWidth > 0) {
			// Set canvas resolution to match display size
			canvas.width = containerWidth;
			canvas.height = height;

			const ctx = canvas.getContext('2d');
			if (ctx) {
				// Fill with dark background initially
				ctx.fillStyle = '#0d1117';
				ctx.fillRect(0, 0, containerWidth, height);
			}
		}
	});

	// Auto-start on mount
	onMount(() => {
		startCapture();
		return () => stopCapture();
	});
</script>

<div class="spectrogram-container" bind:clientWidth={containerWidth}>
	<canvas
		bind:this={canvas}
		style="width: 100%; height: {height}px"
	></canvas>

	<div class="spectrogram-label">
		<span>SPECTROGRAM</span>
		{#if !isRunning && !error}
			<button class="start-btn" onclick={startCapture}>START</button>
		{/if}
	</div>

	{#if error}
		<div class="error-overlay">
			<span>{error}</span>
			<button onclick={startCapture}>Retry</button>
		</div>
	{/if}

	<div class="freq-labels">
		<span class="freq-high">HIGH</span>
		<span class="freq-low">LOW</span>
	</div>
</div>

<style>
	.spectrogram-container {
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

	.spectrogram-label {
		position: absolute;
		top: var(--space-xs);
		left: var(--space-sm);
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		pointer-events: none;
	}

	.spectrogram-label span {
		font-size: 0.6rem;
		font-weight: 600;
		letter-spacing: 0.15em;
		text-transform: uppercase;
		color: var(--text-muted);
		opacity: 0.5;
	}

	.start-btn {
		pointer-events: auto;
		font-size: 0.55rem;
		padding: 2px 6px;
		background: rgba(88, 166, 255, 0.2);
		border: 1px solid rgba(88, 166, 255, 0.4);
		border-radius: 3px;
		color: var(--color-primary, #58a6ff);
		cursor: pointer;
		opacity: 0.8;
	}

	.start-btn:hover {
		opacity: 1;
		background: rgba(88, 166, 255, 0.3);
	}

	.error-overlay {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--space-sm);
		background: rgba(13, 17, 23, 0.9);
		color: var(--color-danger, #f85149);
		font-size: 0.75rem;
	}

	.error-overlay button {
		font-size: 0.7rem;
		padding: 4px 12px;
		background: rgba(88, 166, 255, 0.2);
		border: 1px solid rgba(88, 166, 255, 0.4);
		border-radius: 4px;
		color: var(--color-primary, #58a6ff);
		cursor: pointer;
	}

	.freq-labels {
		position: absolute;
		right: var(--space-sm);
		top: 0;
		bottom: 0;
		display: flex;
		flex-direction: column;
		justify-content: space-between;
		padding: var(--space-xs) 0;
		pointer-events: none;
	}

	.freq-labels span {
		font-size: 0.5rem;
		font-weight: 500;
		letter-spacing: 0.1em;
		color: var(--text-muted);
		opacity: 0.4;
	}
</style>
