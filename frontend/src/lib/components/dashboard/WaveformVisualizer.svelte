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
			analyser.minDecibels = -90;
			analyser.maxDecibels = -10;

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
		if (!canvas || !analyser || !dataArray || !isRunning) return;

		const ctx = canvas.getContext('2d');
		if (!ctx) return;

		// Get frequency data
		analyser.getByteFrequencyData(dataArray);

		// Shift existing image left by 1 pixel
		const imageData = ctx.getImageData(1, 0, canvas.width - 1, canvas.height);
		ctx.putImageData(imageData, 0, 0);

		// Draw new column on right edge
		const binCount = dataArray.length;
		const binHeight = canvas.height / binCount;

		for (let i = 0; i < binCount; i++) {
			const value = dataArray[i];
			const percent = value / 255;

			// Color gradient: dark blue -> cyan -> yellow -> red
			const r = Math.min(255, percent * 2 * 255);
			const g = percent > 0.5 ? 255 - (percent - 0.5) * 2 * 255 : percent * 2 * 255;
			const b = percent < 0.5 ? 255 - percent * 2 * 255 : 0;

			ctx.fillStyle = `rgb(${Math.floor(r)}, ${Math.floor(g)}, ${Math.floor(b)})`;

			// Draw from bottom (low freq) to top (high freq)
			const y = canvas.height - (i + 1) * binHeight;
			ctx.fillRect(canvas.width - 1, y, 1, binHeight);
		}

		animationId = requestAnimationFrame(draw);
	}

	// Setup canvas dimensions
	$effect(() => {
		if (canvas && containerWidth > 0) {
			const dpr = window.devicePixelRatio || 1;
			canvas.width = containerWidth * dpr;
			canvas.height = height * dpr;

			const ctx = canvas.getContext('2d');
			if (ctx) {
				ctx.scale(dpr, dpr);
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
