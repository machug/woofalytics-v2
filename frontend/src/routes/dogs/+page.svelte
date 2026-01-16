<script lang="ts">
	import { onMount } from 'svelte';
	import { api, fetchApi } from '$lib/api/client';
	import type { Dog, Fingerprint, FingerprintStats, DogCreate, DogUpdate, BulkTagResult } from '$lib/api/types';
	import DogCard from '$lib/components/dogs/DogCard.svelte';
	import DogForm from '$lib/components/dogs/DogForm.svelte';
	import BarkModal from '$lib/components/dogs/BarkModal.svelte';
	import UntaggedBarkList from '$lib/components/dogs/UntaggedBarkList.svelte';
	import { toast } from '$lib/stores/toast';

	// State
	let dogs = $state<Dog[]>([]);
	let untaggedBarks = $state<Fingerprint[]>([]);
	let stats = $state<FingerprintStats | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Add dog form state
	let newDogName = $state('');
	let newDogNotes = $state('');
	let addingDog = $state(false);

	// Edit modal state
	let editModalOpen = $state(false);
	let editingDog = $state<Dog | null>(null);

	// Bark modal state
	let barkModalOpen = $state(false);
	let barkModalDog = $state<Dog | null>(null);
	let dogBarks = $state<Fingerprint[]>([]);
	let loadingBarks = $state(false);

	// Computed stats
	let totalDogs = $derived(dogs.length);
	let confirmedDogs = $derived(dogs.filter((d) => d.confirmed).length);
	let untaggedCount = $derived(stats?.untagged ?? untaggedBarks.length);

	async function loadData() {
		loading = true;
		error = null;
		try {
			await Promise.all([loadDogs(), loadUntaggedBarks(), loadStats()]);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load data';
			console.error('Error loading data:', e);
		} finally {
			loading = false;
		}
	}

	async function loadDogs() {
		const response = await api.GET('/api/dogs');
		if (response.error) throw new Error('Failed to load dogs');
		dogs = response.data ?? [];
	}

	async function loadUntaggedBarks() {
		const response = await api.GET('/api/barks/untagged', {
			params: { query: { limit: 20 } }
		});
		if (response.error) throw new Error('Failed to load untagged barks');
		// API returns { count, total_untagged, barks: [...] }
		untaggedBarks = response.data?.barks ?? [];
	}

	async function loadStats() {
		const response = await api.GET('/api/fingerprints/stats');
		if (response.error) throw new Error('Failed to load stats');
		stats = response.data ?? null;
	}

	async function handleAddDog(event: SubmitEvent) {
		event.preventDefault();
		const name = newDogName.trim();
		if (!name) return;

		addingDog = true;
		try {
			const response = await api.POST('/api/dogs', {
				body: {
					name,
					notes: newDogNotes.trim() || undefined
				}
			});

			if (response.error) {
				throw new Error('Failed to add dog');
			}

			newDogName = '';
			newDogNotes = '';
			await loadDogs();
			await loadStats();
		} catch (e) {
			console.error('Error adding dog:', e);
			toast.show('error', 'Failed to add dog. Please try again.');
		} finally {
			addingDog = false;
		}
	}

	function handleEditDog(dog: Dog) {
		editingDog = dog;
		editModalOpen = true;
	}

	async function handleSaveEdit(data: DogCreate | DogUpdate) {
		if (!editingDog) return;

		try {
			const response = await api.PUT('/api/dogs/{dog_id}', {
				params: { path: { dog_id: editingDog.id } },
				body: data as DogUpdate
			});

			if (response.error) {
				throw new Error('Failed to update dog');
			}

			editModalOpen = false;
			editingDog = null;
			await loadDogs();
		} catch (e) {
			console.error('Error updating dog:', e);
			toast.show('error', 'Failed to update dog. Please try again.');
		}
	}

	function handleCancelEdit() {
		editModalOpen = false;
		editingDog = null;
	}

	function handleEditBackdropKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			event.preventDefault();
			handleCancelEdit();
			return;
		}

		if (event.target !== event.currentTarget) return;

		if (event.key === 'Enter' || event.key === ' ') {
			event.preventDefault();
			handleCancelEdit();
		}
	}

	async function handleDeleteDog(dog: Dog) {
		if (!confirm(`Delete "${dog.name}"? This will remove the dog profile but keep the bark recordings.`)) {
			return;
		}

		try {
			const response = await api.DELETE('/api/dogs/{dog_id}', {
				params: { path: { dog_id: dog.id } }
			});

			if (response.error) {
				throw new Error('Failed to delete dog');
			}

			await Promise.all([loadDogs(), loadStats(), loadUntaggedBarks()]);
		} catch (e) {
			console.error('Error deleting dog:', e);
			toast.show('error', 'Failed to delete dog. Please try again.');
		}
	}

	async function handleViewBarks(dog: Dog) {
		barkModalDog = dog;
		barkModalOpen = true;
		loadingBarks = true;
		dogBarks = [];

		try {
			const response = await api.GET('/api/dogs/{dog_id}/barks', {
				params: { path: { dog_id: dog.id } }
			});

			if (response.error) {
				throw new Error('Failed to load barks');
			}

			// API returns { dog_id, dog_name, count, total_barks, barks: [...] }
			dogBarks = response.data?.barks ?? [];
		} catch (e) {
			console.error('Error loading dog barks:', e);
		} finally {
			loadingBarks = false;
		}
	}

	function handleCloseBarkModal() {
		barkModalOpen = false;
		barkModalDog = null;
		dogBarks = [];
	}

	async function handleReassignBark(barkId: string, newDogId: string) {
		try {
			const response = await api.POST('/api/barks/{bark_id}/correct', {
				params: { path: { bark_id: barkId } },
				body: { new_dog_id: newDogId }
			});

			if (response.error) {
				throw new Error('Failed to reassign bark');
			}

			// Remove the bark from the current list
			dogBarks = dogBarks.filter(b => b.id !== barkId);
			await Promise.all([loadDogs(), loadStats()]);
			toast.show('success', 'Bark reassigned successfully');
		} catch (e) {
			console.error('Error reassigning bark:', e);
			toast.show('error', 'Failed to reassign bark. Please try again.');
		}
	}

	async function handleUntagBark(barkId: string) {
		try {
			const response = await api.POST('/api/barks/{bark_id}/untag', {
				params: { path: { bark_id: barkId } }
			});

			if (response.error) {
				throw new Error('Failed to untag bark');
			}

			// Remove the bark from the current list
			dogBarks = dogBarks.filter(b => b.id !== barkId);
			await Promise.all([loadDogs(), loadStats(), loadUntaggedBarks()]);
			toast.show('success', 'Bark unassigned and moved to untagged');
		} catch (e) {
			console.error('Error untagging bark:', e);
			toast.show('error', 'Failed to untag bark. Please try again.');
		}
	}

	async function handleDeleteBark(barkId: string) {
		if (!confirm('Delete this bark? It will be marked as a false positive and hidden from views.')) {
			return;
		}

		try {
			const response = await api.POST('/api/barks/{bark_id}/reject', {
				params: { path: { bark_id: barkId } },
				body: { reason: 'Manually deleted by user' }
			});

			if (response.error) {
				throw new Error('Failed to delete bark');
			}

			// Remove the bark from the current list
			dogBarks = dogBarks.filter(b => b.id !== barkId);
			await Promise.all([loadDogs(), loadStats()]);
			toast.show('success', 'Bark deleted');
		} catch (e) {
			console.error('Error deleting bark:', e);
			toast.show('error', 'Failed to delete bark. Please try again.');
		}
	}

	async function handleToggleConfirm(dog: Dog) {
		try {
			if (dog.confirmed) {
				if (!confirm(`Remove confirmation from "${dog.name}"? This will disable auto-tagging for this dog.`)) {
					return;
				}
				const response = await api.POST('/api/dogs/{dog_id}/unconfirm', {
					params: { path: { dog_id: dog.id } }
				});
				if (response.error) throw new Error('Failed to unconfirm dog');
			} else {
				const response = await api.POST('/api/dogs/{dog_id}/confirm', {
					params: { path: { dog_id: dog.id } },
					body: {}
				});
				if (response.error) throw new Error('Failed to confirm dog');
			}

			await loadDogs();
		} catch (e) {
			console.error('Error toggling confirm:', e);
			toast.show('error', 'Failed to update dog confirmation. Please try again.');
		}
	}

	async function handleTagBark(barkId: string, dogId: string) {
		try {
			const response = await api.POST('/api/barks/{bark_id}/tag', {
				params: { path: { bark_id: barkId } },
				body: { dog_id: dogId }
			});

			if (response.error) {
				throw new Error('Failed to tag bark');
			}

			await Promise.all([loadUntaggedBarks(), loadDogs(), loadStats()]);
		} catch (e) {
			console.error('Error tagging bark:', e);
			toast.show('error', 'Failed to tag bark. Please try again.');
		}
	}

	async function handleBulkTagBarks(barkIds: string[], dogId: string) {
		try {
			const response = await api.POST('/api/barks/bulk-tag', {
				body: { bark_ids: barkIds, dog_id: dogId }
			});

			if (response.error) {
				throw new Error('Failed to bulk tag barks');
			}

			const result = response.data;
			if (result && result.failed_count > 0) {
				console.warn(`Bulk tag: ${result.tagged_count} succeeded, ${result.failed_count} failed`);
			}

			await Promise.all([loadUntaggedBarks(), loadDogs(), loadStats()]);
		} catch (e) {
			console.error('Error bulk tagging barks:', e);
			toast.show('error', 'Failed to tag barks. Please try again.');
		}
	}

	onMount(() => {
		loadData();

		// Refresh every 30 seconds
		const interval = setInterval(loadData, 30000);
		return () => clearInterval(interval);
	});
</script>

<svelte:head>
	<title>Dog Management - Woofalytics</title>
</svelte:head>

<div class="dogs-page">
	<header class="page-header">
		<div class="header-content">
			<svg class="header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<circle cx="12" cy="12" r="10" />
				<path d="M8 14s1.5 2 4 2 4-2 4-2" />
				<line x1="9" y1="9" x2="9.01" y2="9" />
				<line x1="15" y1="9" x2="15.01" y2="9" />
			</svg>
			<h1>Dog Management</h1>
		</div>
	</header>

	<!-- Stats Row -->
	<div class="stats-row">
		<div class="stat-pill stat-pill--dogs">
			<span class="stat-pill-value">{totalDogs}</span>
			<span class="stat-pill-label">Dogs</span>
		</div>
		<div class="stat-pill stat-pill--confirmed">
			<span class="stat-pill-value">{confirmedDogs}</span>
			<span class="stat-pill-label">Confirmed</span>
		</div>
		<div class="stat-pill stat-pill--untagged">
			<span class="stat-pill-value">{untaggedCount}</span>
			<span class="stat-pill-label">Untagged</span>
		</div>
		<div class="stat-pill stat-pill--total">
			<span class="stat-pill-value">{stats?.fingerprints ?? 0}</span>
			<span class="stat-pill-label">Total Barks</span>
		</div>
	</div>

	{#if loading && dogs.length === 0}
		<div class="loading-state">
			<div class="spinner"></div>
			<span>Loading...</span>
		</div>
	{:else if error}
		<div class="error-state">
			<p>{error}</p>
			<button class="btn btn-outline" onclick={loadData}>Retry</button>
		</div>
	{:else}
		<main class="dogs-layout">
			<!-- Dog Profiles Section -->
			<section class="dogs-section">
				<div class="dogs-section-header">
					<h2 class="dogs-section-title">
						<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<circle cx="12" cy="12" r="10" />
							<path d="M8 14s1.5 2 4 2 4-2 4-2" />
							<line x1="9" y1="9" x2="9.01" y2="9" />
							<line x1="15" y1="9" x2="15.01" y2="9" />
						</svg>
						Dog Profiles
					</h2>
					<span class="dogs-section-count">{dogs.length}</span>
				</div>

				<!-- Add Dog Form -->
				<form class="add-dog-form" onsubmit={handleAddDog}>
					<label for="new-dog-name" class="visually-hidden">Dog name</label>
					<input
						type="text"
						id="new-dog-name"
						class="form-input"
						bind:value={newDogName}
						placeholder="Dog name..."
						required
						disabled={addingDog}
					/>
					<label for="new-dog-notes" class="visually-hidden">Notes (optional)</label>
					<input
						type="text"
						id="new-dog-notes"
						class="form-input form-input--notes"
						bind:value={newDogNotes}
						placeholder="Notes (optional)"
						disabled={addingDog}
					/>
					<button type="submit" class="btn-add" title="Add Dog" disabled={addingDog}>
						{#if addingDog}
							<div class="spinner-small"></div>
						{:else}
							<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
								<line x1="12" y1="5" x2="12" y2="19" />
								<line x1="5" y1="12" x2="19" y2="12" />
							</svg>
						{/if}
					</button>
				</form>

				<div class="dogs-section-body">
					{#if dogs.length === 0}
						<div class="empty-state">
							<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
								<circle cx="12" cy="12" r="10" />
								<path d="M8 14s1.5 2 4 2 4-2 4-2" />
								<line x1="9" y1="9" x2="9.01" y2="9" />
								<line x1="15" y1="9" x2="15.01" y2="9" />
							</svg>
							<span>No dogs registered yet.<br />Add your first dog above!</span>
						</div>
					{:else}
						{#each dogs as dog (dog.id)}
							<DogCard
								{dog}
								onEdit={handleEditDog}
								onDelete={handleDeleteDog}
								onViewBarks={handleViewBarks}
								onToggleConfirm={handleToggleConfirm}
							/>
						{/each}
					{/if}
				</div>
			</section>

			<!-- Untagged Barks Section -->
			<section class="dogs-section">
				<div class="dogs-section-header">
					<h2 class="dogs-section-title">
						<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<path d="M11 5L6 9H2v6h4l5 4V5z" />
							<path d="M15.54 8.46a5 5 0 010 7.07" />
						</svg>
						Untagged Barks
					</h2>
					<span class="dogs-section-count">{untaggedBarks.length}</span>
				</div>

				<div class="dogs-section-body">
					<UntaggedBarkList barks={untaggedBarks} {dogs} onTag={handleTagBark} onBulkTag={handleBulkTagBarks} />
				</div>
			</section>
		</main>
	{/if}
</div>

<!-- Edit Dog Modal -->
{#if editModalOpen && editingDog}
	<div
		class="modal-backdrop active"
		role="presentation"
		onclick={(event) => event.target === event.currentTarget && handleCancelEdit()}
		onkeydown={handleEditBackdropKeydown}
	>
		<div class="modal">
			<h3 class="modal-title">
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
					<path d="M18.5 2.5a2.12 2.12 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
				</svg>
				Edit Dog Profile
			</h3>
			<DogForm dog={editingDog} onSubmit={handleSaveEdit} onCancel={handleCancelEdit} />
		</div>
	</div>
{/if}

<!-- View Barks Modal -->
{#if barkModalDog}
	<BarkModal
		bind:open={barkModalOpen}
		dogName={barkModalDog.name}
		dogId={barkModalDog.id}
		barks={dogBarks}
		{dogs}
		onClose={handleCloseBarkModal}
		onReassign={handleReassignBark}
		onUntag={handleUntagBark}
		onDelete={handleDeleteBark}
	/>
{/if}

<style>
	.dogs-page {
		width: 100%;
	}

	.page-header {
		margin-bottom: var(--space-lg);
	}

	.header-content {
		display: flex;
		align-items: center;
		gap: var(--space-md);
	}

	.header-icon {
		width: 32px;
		height: 32px;
		color: var(--accent-amber);
	}

	.page-header h1 {
		font-size: 1.5rem;
		font-weight: 700;
		color: var(--text-primary);
		margin: 0;
	}

	/* Stats Row */
	.stats-row {
		display: flex;
		gap: var(--space-md);
		margin-bottom: var(--space-lg);
		padding: var(--space-md) var(--space-lg);
		background: rgba(22, 27, 34, 0.6);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-lg);
		backdrop-filter: blur(20px);
		flex-wrap: wrap;
	}

	.stat-pill {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-xs) var(--space-md);
		background: var(--bg-overlay);
		border-radius: var(--radius-full);
	}

	.stat-pill-value {
		font-size: 1.25rem;
		font-weight: 700;
		font-family: 'JetBrains Mono', monospace;
		color: var(--text-primary);
	}

	.stat-pill-label {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.stat-pill--dogs .stat-pill-value {
		color: var(--accent-amber);
	}
	.stat-pill--confirmed .stat-pill-value {
		color: #10b981;
	}
	.stat-pill--untagged .stat-pill-value {
		color: var(--accent-coral);
	}
	.stat-pill--total .stat-pill-value {
		color: var(--accent-teal);
	}

	/* Main Layout */
	.dogs-layout {
		display: grid;
		grid-template-columns: 1.2fr 1fr;
		gap: var(--space-lg);
	}

	@media (max-width: 1100px) {
		.dogs-layout {
			grid-template-columns: 1fr;
		}
	}

	/* Section Panels */
	.dogs-section {
		display: flex;
		flex-direction: column;
		background: rgba(22, 27, 34, 0.6);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-lg);
		backdrop-filter: blur(20px);
		overflow: hidden;
	}

	.dogs-section-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--space-md) var(--space-lg);
		border-bottom: 1px solid var(--border-muted);
		background: rgba(0, 0, 0, 0.2);
	}

	.dogs-section-title {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.dogs-section-title svg {
		width: 18px;
		height: 18px;
		color: var(--accent-amber);
	}

	.dogs-section-count {
		font-size: 0.7rem;
		font-weight: 600;
		padding: 2px 8px;
		background: var(--bg-overlay);
		border-radius: var(--radius-full);
		color: var(--text-muted);
	}

	.dogs-section-body {
		flex: 1;
		padding: var(--space-md);
		overflow-y: auto;
		max-height: 600px;
	}

	/* Add Dog Form */
	.add-dog-form {
		display: flex;
		gap: var(--space-sm);
		padding: var(--space-sm) var(--space-md);
		margin: var(--space-sm);
		background: var(--bg-overlay);
		border-radius: var(--radius-md);
		border: 1px dashed var(--border-default);
	}

	.add-dog-form .form-input {
		flex: 1;
		padding: var(--space-sm) var(--space-md);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		color: var(--text-primary);
		font-size: 0.875rem;
		min-width: 0;
	}

	.add-dog-form .form-input--notes {
		flex: 0.8;
	}

	.add-dog-form .form-input:focus {
		outline: none;
		border-color: var(--accent-amber);
	}

	.add-dog-form .form-input::placeholder {
		color: var(--text-muted);
	}

	.add-dog-form .form-input:disabled {
		opacity: 0.6;
	}

	.btn-add {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 36px;
		height: 36px;
		background: var(--accent-amber);
		border: none;
		border-radius: var(--radius-sm);
		color: var(--bg-base);
		cursor: pointer;
		transition: all var(--transition-fast);
		flex-shrink: 0;
	}

	.btn-add:hover:not(:disabled) {
		background: #fbbf24;
		transform: scale(1.05);
	}

	.btn-add:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-add svg {
		width: 18px;
		height: 18px;
	}

	/* Loading & Error States */
	.loading-state {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-sm);
		padding: var(--space-2xl);
		color: var(--text-muted);
	}

	.error-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-md);
		padding: var(--space-2xl);
		color: var(--accent-coral);
		text-align: center;
	}

	.spinner-small {
		width: 16px;
		height: 16px;
		border: 2px solid var(--bg-base);
		border-top-color: transparent;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	/* Modal Styles */
	.modal-title {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		font-size: 1.1rem;
		font-weight: 600;
		margin-bottom: var(--space-lg);
	}

	.modal-title svg {
		width: 20px;
		height: 20px;
		color: var(--accent-amber);
	}

	/* Empty States */
	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: var(--space-2xl) var(--space-lg);
		text-align: center;
		color: var(--text-muted);
		font-size: 0.875rem;
		line-height: 1.5;
	}

	.empty-state svg {
		width: 48px;
		height: 48px;
		margin-bottom: var(--space-md);
		opacity: 0.4;
	}

	@media (max-width: 768px) {
		.stats-row {
			gap: var(--space-sm);
		}

		.add-dog-form {
			flex-wrap: wrap;
		}

		.add-dog-form .form-input {
			flex: 1 1 100%;
		}

		.add-dog-form .form-input--notes {
			flex: 1 1 calc(100% - 44px);
		}
	}
</style>
