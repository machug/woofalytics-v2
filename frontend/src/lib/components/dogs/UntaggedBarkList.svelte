<script lang="ts">
	import type { Dog, Fingerprint } from '$lib/api/types';

	interface Props {
		barks: Fingerprint[];
		dogs: Dog[];
		onTag: (barkId: string, dogId: string) => void;
	}

	let { barks, dogs, onTag }: Props = $props();

	let openDropdownId = $state<string | null>(null);
	let currentlyPlaying = $state<string | null>(null);
	let audioElement = $state<HTMLAudioElement | null>(null);

	function formatTime(dateStr: string): string {
		const date = new Date(dateStr);
		return date.toLocaleString('en-US', {
			month: 'short',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit',
			hour12: true
		});
	}

	function toggleDropdown(barkId: string, event: MouseEvent) {
		event.stopPropagation();
		openDropdownId = openDropdownId === barkId ? null : barkId;
	}

	function closeDropdowns() {
		openDropdownId = null;
	}

	function handleTag(barkId: string, dogId: string) {
		closeDropdowns();
		onTag(barkId, dogId);
	}

	function playAudio(bark: Fingerprint) {
		if (!bark.evidence_file) return;

		stopAudio();

		const audioUrl = `/api/evidence/${bark.evidence_file}?format=opus`;
		audioElement = new Audio(audioUrl);
		audioElement.onended = () => {
			currentlyPlaying = null;
		};
		audioElement.onerror = () => {
			currentlyPlaying = null;
			console.error('Error playing audio');
		};
		audioElement.play();
		currentlyPlaying = bark.id;
	}

	function stopAudio() {
		if (audioElement) {
			audioElement.pause();
			audioElement.currentTime = 0;
			audioElement = null;
		}
		currentlyPlaying = null;
	}

	function toggleAudio(bark: Fingerprint, event: MouseEvent) {
		event.stopPropagation();
		if (currentlyPlaying === bark.id) {
			stopAudio();
		} else {
			playAudio(bark);
		}
	}
</script>

<svelte:window onclick={closeDropdowns} />

<div class="untagged-barks">
	{#if barks.length === 0}
		<div class="empty-state">
			<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
				<path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
				<polyline points="22 4 12 14.01 9 11.01" />
			</svg>
			<span>All barks have been reviewed!</span>
		</div>
	{:else}
		{#each barks as bark (bark.id)}
			<div class="bark-card">
				<div class="bark-icon">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M11 5L6 9H2v6h4l5 4V5z" />
						<path d="M15.54 8.46a5 5 0 010 7.07" />
					</svg>
				</div>

				<div class="bark-content">
					<div class="bark-header">
						<span class="bark-time">{formatTime(bark.timestamp)}</span>
						<span class="bark-prob">
							{(bark.confidence * 100).toFixed(0)}%
						</span>
					</div>
					<div class="bark-meta">
						{#if bark.evidence_file}
							<button class="play-link" onclick={(e) => toggleAudio(bark, e)}>
								{#if currentlyPlaying === bark.id}
									Stop
								{:else}
									Play recording
								{/if}
							</button>
						{/if}
						<span>Duration: {bark.duration_ms}ms</span>
					</div>
				</div>

				{#if dogs.length > 0}
					<div class="tag-select" class:open={openDropdownId === bark.id}>
						<button
							class="tag-select-trigger"
							onclick={(e) => toggleDropdown(bark.id, e)}
						>
							Assign to dog
							<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<polyline points="6 9 12 15 18 9" />
							</svg>
						</button>
						<div class="tag-select-menu">
							{#each dogs as dog (dog.id)}
								<button
									class="tag-option"
									onclick={() => handleTag(bark.id, dog.id)}
								>
									{dog.emoji || '🐕'} {dog.name}
								</button>
							{/each}
						</div>
					</div>
				{:else}
					<span class="no-dogs-hint">Add dogs first</span>
				{/if}
			</div>
		{/each}
	{/if}
</div>

<style>
	.untagged-barks {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
	}

	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: var(--space-2xl) var(--space-lg);
		text-align: center;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.empty-state svg {
		width: 48px;
		height: 48px;
		margin-bottom: var(--space-md);
		opacity: 0.4;
	}

	.bark-card {
		display: flex;
		align-items: flex-start;
		gap: var(--space-md);
		padding: var(--space-md);
		background: var(--bg-overlay);
		border-radius: var(--radius-md);
		border-left: 3px solid var(--accent-coral);
		transition: all var(--transition-fast);
	}

	.bark-card:hover {
		background: rgba(28, 33, 40, 0.8);
	}

	.bark-icon {
		width: 32px;
		height: 32px;
		border-radius: var(--radius-sm);
		background: var(--accent-coral-dim);
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}

	.bark-icon svg {
		width: 16px;
		height: 16px;
		color: var(--accent-coral);
	}

	.bark-content {
		flex: 1;
		min-width: 0;
	}

	.bark-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-sm);
		margin-bottom: 4px;
	}

	.bark-time {
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--text-primary);
		font-family: 'JetBrains Mono', monospace;
	}

	.bark-prob {
		font-size: 0.65rem;
		font-weight: 600;
		padding: 2px 6px;
		background: var(--accent-teal-dim);
		color: var(--accent-teal);
		border-radius: var(--radius-full);
	}

	.bark-meta {
		display: flex;
		gap: var(--space-md);
		font-size: 0.7rem;
		color: var(--text-muted);
	}

	.play-link {
		background: none;
		border: none;
		color: var(--accent-blue);
		cursor: pointer;
		font-size: inherit;
		padding: 0;
		text-decoration: none;
	}

	.play-link:hover {
		text-decoration: underline;
	}

	.tag-select {
		position: relative;
		min-width: 140px;
		flex-shrink: 0;
	}

	.tag-select-trigger {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-sm);
		width: 100%;
		padding: var(--space-sm) var(--space-md);
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-secondary);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.tag-select-trigger:hover {
		border-color: var(--accent-amber);
		color: var(--text-primary);
	}

	.tag-select-trigger svg {
		width: 12px;
		height: 12px;
		transition: transform var(--transition-fast);
	}

	.tag-select.open .tag-select-trigger svg {
		transform: rotate(180deg);
	}

	.tag-select-menu {
		position: absolute;
		top: 100%;
		left: 0;
		right: 0;
		margin-top: 4px;
		padding: var(--space-xs);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-lg);
		z-index: 100;
		opacity: 0;
		visibility: hidden;
		transform: translateY(-8px);
		transition: all var(--transition-fast);
		max-height: 200px;
		overflow-y: auto;
	}

	.tag-select.open .tag-select-menu {
		opacity: 1;
		visibility: visible;
		transform: translateY(0);
	}

	.tag-option {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		width: 100%;
		padding: var(--space-sm) var(--space-md);
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-secondary);
		background: transparent;
		border: none;
		border-radius: var(--radius-sm);
		cursor: pointer;
		transition: all var(--transition-fast);
		text-align: left;
	}

	.tag-option:hover {
		background: var(--accent-amber-dim);
		color: var(--accent-amber);
	}

	.no-dogs-hint {
		font-size: 0.75rem;
		color: var(--text-muted);
		flex-shrink: 0;
	}

	@media (max-width: 600px) {
		.bark-card {
			flex-wrap: wrap;
		}

		.tag-select {
			width: 100%;
			margin-top: var(--space-sm);
		}
	}
</style>
