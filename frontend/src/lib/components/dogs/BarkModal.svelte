<script lang="ts">
	import type { Fingerprint, Dog } from '$lib/api/types';

	interface Props {
		open: boolean;
		dogName: string;
		dogId: string;
		barks: Fingerprint[];
		dogs: Dog[];
		onClose: () => void;
		onReassign?: (barkId: string, newDogId: string) => void;
		onUntag?: (barkId: string) => void;
		onDelete?: (barkId: string) => void;
	}

	let { open = $bindable(false), dogName, dogId, barks, dogs, onClose, onReassign, onUntag, onDelete }: Props = $props();

	let openDropdown = $state<string | null>(null);

	// Filter out the current dog from the reassignment options
	let otherDogs = $derived(dogs.filter(d => d.id !== dogId));

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

	function handleBackdropClick(event: MouseEvent) {
		if (event.target === event.currentTarget) {
			handleClose();
		}
	}

	function handleClose() {
		stopAudio();
		open = false;
		onClose();
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			handleClose();
		}
	}

	function playAudio(bark: Fingerprint) {
		if (!bark.evidence_filename) return;

		// Stop current audio if playing
		stopAudio();

		const audioUrl = `/api/evidence/${bark.evidence_filename}?format=opus`;
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

	function toggleAudio(bark: Fingerprint) {
		if (currentlyPlaying === bark.id) {
			stopAudio();
		} else {
			playAudio(bark);
		}
	}

	function toggleDropdown(barkId: string) {
		openDropdown = openDropdown === barkId ? null : barkId;
	}

	function handleReassign(barkId: string, newDogId: string) {
		openDropdown = null;
		onReassign?.(barkId, newDogId);
	}

	function handleUntag(barkId: string) {
		onUntag?.(barkId);
	}

	function handleDelete(barkId: string) {
		onDelete?.(barkId);
	}

	function closeDropdowns() {
		openDropdown = null;
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- svelte-ignore a11y_click_events_have_key_events -->
<div class="modal-backdrop" class:active={open} onclick={handleBackdropClick} role="dialog" aria-modal="true" tabindex="-1">
	<div class="modal-container">
		<div class="modal-header">
			<h3 class="modal-title">
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<path d="M11 5L6 9H2v6h4l5 4V5z" />
					<path d="M15.54 8.46a5 5 0 010 7.07" />
				</svg>
				<span>{dogName}'s Barks ({barks.length})</span>
			</h3>
			<button type="button" class="modal-close" onclick={handleClose} aria-label="Close modal">
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<line x1="18" y1="6" x2="6" y2="18" />
					<line x1="6" y1="6" x2="18" y2="18" />
				</svg>
			</button>
		</div>

		<div class="modal-body">
			{#if barks.length === 0}
				<div class="empty-state">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
						<path d="M11 5L6 9H2v6h4l5 4V5z" />
					</svg>
					<span>No barks recorded for this dog yet.</span>
				</div>
			{:else}
				<div class="barks-list">
					{#each barks as bark (bark.id)}
						<div class="bark-item">
							<div class="bark-icon">
								<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<path d="M11 5L6 9H2v6h4l5 4V5z" />
								</svg>
							</div>

							<div class="bark-content">
								<div class="bark-header">
									<span class="bark-time">{formatTime(bark.timestamp)}</span>
									<span class="bark-confidence">
										{(bark.detection_probability * 100).toFixed(0)}%
									</span>
								</div>
								<div class="bark-meta">
									<span>Duration: {bark.duration_ms}ms</span>
									{#if bark.pitch_hz}
										<span>Pitch: {bark.pitch_hz.toFixed(0)}Hz</span>
									{/if}
								</div>
							</div>

							<div class="bark-actions">
								{#if bark.evidence_filename}
									<button
										class="btn-action btn-play"
										class:playing={currentlyPlaying === bark.id}
										onclick={() => toggleAudio(bark)}
										title="Play audio"
									>
										{#if currentlyPlaying === bark.id}
											<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
												<rect x="6" y="4" width="4" height="16" />
												<rect x="14" y="4" width="4" height="16" />
											</svg>
										{:else}
											<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
												<polygon points="5 3 19 12 5 21 5 3" />
											</svg>
										{/if}
									</button>
								{/if}

								<!-- Reassign Dropdown -->
								{#if otherDogs.length > 0}
									<div class="dropdown-container">
										<button
											class="btn-action btn-reassign"
											onclick={() => toggleDropdown(bark.id)}
											title="Reassign to another dog"
										>
											<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
												<path d="M16 3h5v5" />
												<path d="M4 20L21 3" />
												<path d="M21 16v5h-5" />
												<path d="M15 15l6 6" />
												<path d="M4 4l5 5" />
											</svg>
										</button>
										{#if openDropdown === bark.id}
											<div class="dropdown-menu">
												<div class="dropdown-header">Reassign to:</div>
												{#each otherDogs as dog (dog.id)}
													<button
														class="dropdown-item"
														onclick={() => handleReassign(bark.id, dog.id)}
													>
														{dog.name}
													</button>
												{/each}
												<div class="dropdown-divider"></div>
												<button
													class="dropdown-item dropdown-item--untag"
													onclick={() => handleUntag(bark.id)}
												>
													Unassign (move to untagged)
												</button>
											</div>
										{/if}
									</div>
								{:else}
									<button
										class="btn-action btn-untag"
										onclick={() => handleUntag(bark.id)}
										title="Unassign bark"
									>
										<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
											<path d="M18.36 6.64a9 9 0 11-12.73 0" />
											<line x1="12" y1="2" x2="12" y2="12" />
										</svg>
									</button>
								{/if}

								<!-- Delete Button -->
								<button
									class="btn-action btn-delete"
									onclick={() => handleDelete(bark.id)}
									title="Delete bark (mark as false positive)"
								>
									<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
										<polyline points="3 6 5 6 21 6" />
										<path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
										<line x1="10" y1="11" x2="10" y2="17" />
										<line x1="14" y1="11" x2="14" y2="17" />
									</svg>
								</button>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>

		<div class="modal-footer">
			<button type="button" class="btn btn-outline" onclick={handleClose}>Close</button>
		</div>
	</div>
</div>

<style>
	.modal-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.7);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 2000;
		opacity: 0;
		visibility: hidden;
		transition: all var(--transition-base);
	}

	.modal-backdrop.active {
		opacity: 1;
		visibility: visible;
	}

	.modal-container {
		max-width: 640px;
		width: 95%;
		max-height: 85vh;
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-lg);
		box-shadow: var(--shadow-lg), 0 0 0 1px rgba(20, 184, 166, 0.1);
		display: flex;
		flex-direction: column;
		overflow: hidden;
		transform: scale(0.95);
		transition: transform var(--transition-base);
	}

	.modal-backdrop.active .modal-container {
		transform: scale(1);
	}

	.modal-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--space-md) var(--space-lg);
		border-bottom: 1px solid var(--border-muted);
		background: rgba(0, 0, 0, 0.3);
	}

	.modal-title {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		font-size: 1rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.modal-title svg {
		width: 20px;
		height: 20px;
		color: var(--accent-teal);
	}

	.modal-close {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 28px;
		height: 28px;
		background: transparent;
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		color: var(--text-muted);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.modal-close:hover {
		background: var(--bg-overlay);
		color: var(--text-primary);
	}

	.modal-close svg {
		width: 14px;
		height: 14px;
	}

	.modal-body {
		flex: 1;
		padding: var(--space-md) var(--space-lg);
		overflow-y: auto;
	}

	.modal-footer {
		padding: var(--space-md) var(--space-lg);
		border-top: 1px solid var(--border-muted);
		background: rgba(0, 0, 0, 0.2);
		display: flex;
		justify-content: flex-end;
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
	}

	.empty-state svg {
		width: 48px;
		height: 48px;
		margin-bottom: var(--space-md);
		opacity: 0.4;
	}

	.barks-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
	}

	.bark-item {
		display: flex;
		align-items: center;
		gap: var(--space-md);
		padding: var(--space-md);
		background: var(--bg-overlay);
		border-radius: var(--radius-md);
		border-left: 3px solid var(--accent-teal);
	}

	.bark-icon {
		width: 32px;
		height: 32px;
		border-radius: var(--radius-sm);
		background: var(--accent-teal-dim);
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}

	.bark-icon svg {
		width: 16px;
		height: 16px;
		color: var(--accent-teal);
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

	.bark-confidence {
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

	/* Action buttons container */
	.bark-actions {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		flex-shrink: 0;
	}

	.btn-action {
		width: 32px;
		height: 32px;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg-overlay);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		color: var(--text-muted);
		cursor: pointer;
		transition: all var(--transition-fast);
		flex-shrink: 0;
	}

	.btn-action svg {
		width: 14px;
		height: 14px;
	}

	.btn-action:hover {
		background: var(--bg-surface);
		color: var(--text-primary);
		border-color: var(--border-subtle);
	}

	.btn-play {
		background: var(--accent-teal-dim);
		border-color: var(--accent-teal);
		color: var(--accent-teal);
	}

	.btn-play:hover {
		background: var(--accent-teal);
		color: var(--bg-base);
	}

	.btn-play.playing {
		background: var(--accent-amber);
		border-color: var(--accent-amber);
		color: var(--bg-base);
	}

	.btn-reassign:hover {
		border-color: var(--accent-amber);
		color: var(--accent-amber);
	}

	.btn-untag:hover {
		border-color: var(--accent-amber);
		color: var(--accent-amber);
	}

	.btn-delete:hover {
		border-color: var(--accent-coral);
		color: var(--accent-coral);
	}

	/* Dropdown */
	.dropdown-container {
		position: relative;
	}

	.dropdown-menu {
		position: absolute;
		top: 100%;
		right: 0;
		margin-top: var(--space-xs);
		min-width: 180px;
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-lg);
		z-index: 100;
		overflow: hidden;
	}

	.dropdown-header {
		padding: var(--space-xs) var(--space-sm);
		font-size: 0.65rem;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		background: rgba(0, 0, 0, 0.2);
		border-bottom: 1px solid var(--border-muted);
	}

	.dropdown-item {
		display: block;
		width: 100%;
		padding: var(--space-sm) var(--space-md);
		background: transparent;
		border: none;
		text-align: left;
		font-size: 0.8rem;
		color: var(--text-primary);
		cursor: pointer;
		transition: background var(--transition-fast);
	}

	.dropdown-item:hover {
		background: var(--bg-overlay);
	}

	.dropdown-item--untag {
		color: var(--accent-amber);
	}

	.dropdown-item--untag:hover {
		background: rgba(251, 191, 36, 0.1);
	}

	.dropdown-divider {
		height: 1px;
		background: var(--border-muted);
		margin: var(--space-xs) 0;
	}
</style>
