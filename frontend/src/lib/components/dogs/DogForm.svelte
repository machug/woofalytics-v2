<script lang="ts">
	import type { Dog, DogCreate, DogUpdate } from '$lib/api/types';

	interface Props {
		dog?: Dog | null;
		onSubmit: (data: DogCreate | DogUpdate) => void;
		onCancel: () => void;
	}

	let { dog = null, onSubmit, onCancel }: Props = $props();

	const isEditMode = $derived(!!dog);

	let name = $state(dog?.name ?? '');
	let notes = $state(dog?.notes ?? '');
	let emoji = $state(dog?.emoji ?? '🐕');
	let error = $state('');

	const commonEmojis = ['🐕', '🐶', '🐩', '🦮', '🐕‍🦺', '🐾', '🦴', '🎾'];

	function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		error = '';

		const trimmedName = name.trim();
		if (!trimmedName) {
			error = 'Dog name is required';
			return;
		}

		const data: DogCreate | DogUpdate = {
			name: trimmedName,
			notes: notes.trim() || undefined,
			emoji: emoji
		};

		onSubmit(data);
	}

	function selectEmoji(e: string) {
		emoji = e;
	}
</script>

<form class="dog-form" onsubmit={handleSubmit}>
	<div class="form-group">
		<label class="form-label" for="dog-name">Dog Name *</label>
		<input
			type="text"
			id="dog-name"
			class="form-input"
			bind:value={name}
			placeholder="Enter dog's name"
			required
		/>
	</div>

	<div class="form-group">
		<label class="form-label" for="dog-notes">Notes</label>
		<textarea
			id="dog-notes"
			class="form-input form-textarea"
			bind:value={notes}
			placeholder="Optional notes about this dog"
			rows="3"
		></textarea>
	</div>

	<div class="form-group">
		<span class="form-label" id="emoji-label">Avatar Emoji</span>
		<div class="emoji-picker" role="radiogroup" aria-labelledby="emoji-label">
			{#each commonEmojis as e}
				<button
					type="button"
					class="emoji-btn"
					class:selected={emoji === e}
					onclick={() => selectEmoji(e)}
					aria-label={`Select ${e} emoji`}
					aria-pressed={emoji === e}
				>
					{e}
				</button>
			{/each}
		</div>
	</div>

	{#if error}
		<div class="form-error">{error}</div>
	{/if}

	<div class="form-actions">
		<button type="button" class="btn btn-outline" onclick={onCancel}>Cancel</button>
		<button type="submit" class="btn btn-amber">
			{isEditMode ? 'Save Changes' : 'Add Dog'}
		</button>
	</div>
</form>

<style>
	.dog-form {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}

	.form-group {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}

	.form-label {
		font-size: 0.75rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-secondary);
	}

	.form-input {
		width: 100%;
		padding: var(--space-sm) var(--space-md);
		background: var(--bg-overlay);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		color: var(--text-primary);
		font-size: 0.875rem;
		transition: border-color var(--transition-fast);
	}

	.form-input:focus {
		outline: none;
		border-color: var(--accent-amber);
	}

	.form-input::placeholder {
		color: var(--text-muted);
	}

	.form-textarea {
		resize: vertical;
		min-height: 80px;
	}

	.emoji-picker {
		display: flex;
		gap: var(--space-xs);
		flex-wrap: wrap;
	}

	.emoji-btn {
		width: 40px;
		height: 40px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1.25rem;
		background: var(--bg-overlay);
		border: 2px solid var(--border-default);
		border-radius: var(--radius-sm);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.emoji-btn:hover {
		background: var(--bg-elevated);
		border-color: var(--text-muted);
	}

	.emoji-btn.selected {
		background: var(--accent-amber-dim);
		border-color: var(--accent-amber);
	}

	.form-error {
		padding: var(--space-sm) var(--space-md);
		background: var(--accent-coral-dim);
		border: 1px solid rgba(248, 81, 73, 0.3);
		border-radius: var(--radius-sm);
		color: var(--accent-coral);
		font-size: 0.8rem;
	}

	.form-actions {
		display: flex;
		justify-content: flex-end;
		gap: var(--space-sm);
		margin-top: var(--space-sm);
	}
</style>
