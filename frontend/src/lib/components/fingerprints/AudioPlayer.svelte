<script lang="ts">
	/**
	 * AudioPlayer - Inline audio player for evidence files
	 * Manages a single audio instance - pauses others when playing
	 */

	interface Props {
		src: string;
		onClose?: () => void;
	}

	let { src, onClose }: Props = $props();

	let audioElement: HTMLAudioElement | null = $state(null);
	let isPlaying = $state(false);
	let progress = $state(0);
	let duration = $state(0);
	let currentTime = $state(0);
	let isLoading = $state(true);
	let hasError = $state(false);

	// Global audio manager - pause all other players when this one starts
	const pauseOtherPlayers = () => {
		document.querySelectorAll('audio').forEach((audio) => {
			if (audio !== audioElement) {
				audio.pause();
			}
		});
	};

	const handlePlay = () => {
		if (!audioElement) return;
		pauseOtherPlayers();
		audioElement.play().catch(() => {
			hasError = true;
		});
	};

	const handlePause = () => {
		audioElement?.pause();
	};

	const togglePlay = () => {
		if (isPlaying) {
			handlePause();
		} else {
			handlePlay();
		}
	};

	const handleTimeUpdate = () => {
		if (!audioElement) return;
		currentTime = audioElement.currentTime;
		if (duration > 0) {
			progress = (currentTime / duration) * 100;
		}
	};

	const handleLoadedMetadata = () => {
		if (!audioElement) return;
		duration = audioElement.duration;
		isLoading = false;
	};

	const handleEnded = () => {
		isPlaying = false;
		progress = 0;
		currentTime = 0;
	};

	const handleError = () => {
		hasError = true;
		isLoading = false;
	};

	const handleSeek = (event: MouseEvent) => {
		if (!audioElement || duration === 0) return;
		const bar = event.currentTarget as HTMLElement;
		const rect = bar.getBoundingClientRect();
		const x = event.clientX - rect.left;
		const percentage = x / rect.width;
		audioElement.currentTime = percentage * duration;
	};

	const formatTime = (seconds: number): string => {
		if (!isFinite(seconds)) return '0:00';
		const mins = Math.floor(seconds / 60);
		const secs = Math.floor(seconds % 60);
		return `${mins}:${secs.toString().padStart(2, '0')}`;
	};

	// Build the audio URL
	const audioUrl = $derived(`/api/evidence/${src}?format=opus`);
	const fallbackUrl = $derived(`/api/evidence/${src}`);
</script>

<div class="audio-player" class:has-error={hasError}>
	<audio
		bind:this={audioElement}
		src={audioUrl}
		preload="metadata"
		onplay={() => (isPlaying = true)}
		onpause={() => (isPlaying = false)}
		ontimeupdate={handleTimeUpdate}
		onloadedmetadata={handleLoadedMetadata}
		onended={handleEnded}
		onerror={handleError}
	></audio>

	{#if hasError}
		<div class="error-state">
			<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<circle cx="12" cy="12" r="10" />
				<line x1="15" y1="9" x2="9" y2="15" />
				<line x1="9" y1="9" x2="15" y2="15" />
			</svg>
			<span>Failed to load audio</span>
		</div>
	{:else}
		<button
			class="play-btn"
			onclick={togglePlay}
			disabled={isLoading}
			aria-label={isPlaying ? 'Pause' : 'Play'}
		>
			{#if isLoading}
				<div class="spinner"></div>
			{:else if isPlaying}
				<svg viewBox="0 0 24 24" fill="currentColor">
					<rect x="6" y="4" width="4" height="16" />
					<rect x="14" y="4" width="4" height="16" />
				</svg>
			{:else}
				<svg viewBox="0 0 24 24" fill="currentColor">
					<polygon points="5 3 19 12 5 21 5 3" />
				</svg>
			{/if}
		</button>

		<div class="progress-container">
			<div class="time-display">
				<span class="current-time">{formatTime(currentTime)}</span>
				<span class="separator">/</span>
				<span class="duration">{formatTime(duration)}</span>
			</div>

			<!-- svelte-ignore a11y_click_events_have_key_events -->
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div class="progress-bar" onclick={handleSeek}>
				<div class="progress-track"></div>
				<div class="progress-fill" style="width: {progress}%"></div>
				<div class="progress-handle" style="left: {progress}%"></div>
			</div>
		</div>
	{/if}

	{#if onClose}
		<button class="close-btn" onclick={onClose} aria-label="Close player">
			<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<line x1="18" y1="6" x2="6" y2="18" />
				<line x1="6" y1="6" x2="18" y2="18" />
			</svg>
		</button>
	{/if}
</div>

<style>
	.audio-player {
		display: flex;
		align-items: center;
		gap: var(--space-md);
		padding: var(--space-sm) var(--space-md);
		background: var(--bg-overlay);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
		min-width: 280px;
	}

	.audio-player.has-error {
		border-color: rgba(248, 81, 73, 0.3);
	}

	.play-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 36px;
		height: 36px;
		background: var(--accent-amber-dim);
		border: 1px solid var(--accent-amber);
		border-radius: 50%;
		color: var(--accent-amber);
		cursor: pointer;
		transition: all var(--transition-fast);
		flex-shrink: 0;
	}

	.play-btn:hover:not(:disabled) {
		background: var(--accent-amber);
		color: var(--bg-base);
		transform: scale(1.05);
	}

	.play-btn:disabled {
		opacity: 0.6;
		cursor: wait;
	}

	.play-btn svg {
		width: 16px;
		height: 16px;
	}

	.progress-container {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.time-display {
		display: flex;
		align-items: center;
		gap: 4px;
		font-size: 0.75rem;
		font-family: 'JetBrains Mono', monospace;
		color: var(--text-muted);
	}

	.current-time {
		color: var(--text-primary);
	}

	.separator {
		opacity: 0.5;
	}

	.progress-bar {
		position: relative;
		height: 6px;
		cursor: pointer;
		border-radius: 3px;
	}

	.progress-track {
		position: absolute;
		inset: 0;
		background: var(--border-default);
		border-radius: 3px;
	}

	.progress-fill {
		position: absolute;
		top: 0;
		left: 0;
		bottom: 0;
		background: var(--accent-amber);
		border-radius: 3px;
		transition: width 0.1s linear;
	}

	.progress-handle {
		position: absolute;
		top: 50%;
		transform: translate(-50%, -50%);
		width: 12px;
		height: 12px;
		background: var(--accent-amber);
		border: 2px solid var(--bg-surface);
		border-radius: 50%;
		opacity: 0;
		transition: opacity var(--transition-fast);
	}

	.progress-bar:hover .progress-handle {
		opacity: 1;
	}

	.close-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 24px;
		height: 24px;
		background: transparent;
		border: none;
		color: var(--text-muted);
		cursor: pointer;
		transition: color var(--transition-fast);
		flex-shrink: 0;
	}

	.close-btn:hover {
		color: var(--text-primary);
	}

	.close-btn svg {
		width: 16px;
		height: 16px;
	}

	.error-state {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		color: var(--accent-coral);
		font-size: 0.875rem;
	}

	.error-state svg {
		width: 20px;
		height: 20px;
	}

	.spinner {
		width: 16px;
		height: 16px;
		border: 2px solid var(--border-default);
		border-top-color: var(--accent-amber);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
</style>
