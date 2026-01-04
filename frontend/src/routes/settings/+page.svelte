<script lang="ts">
	import { api, fetchApi } from '$lib/api/client';
	import type { EvidenceStats, FingerprintStats, Dog, PurgeResult, RecalculateResult } from '$lib/api/types';

	// Stats state
	let evidenceStats = $state<EvidenceStats | null>(null);
	let fingerprintStats = $state<FingerprintStats | null>(null);
	let dogs = $state<Dog[]>([]);
	let isLoadingStats = $state(true);

	// Form state
	let evidenceBeforeDate = $state('');
	let fingerprintsBeforeDate = $state('');
	let untaggedOnly = $state(true);

	// Loading states
	let isPurgingEvidence = $state(false);
	let isPurgingFingerprints = $state(false);
	let isRecalculating = $state(false);

	// Modal state
	let showModal = $state(false);
	let modalTitle = $state('');
	let modalMessage = $state('');
	let modalStats = $state<{ label: string; value: string }[]>([]);
	let pendingAction = $state<'evidence' | 'fingerprints' | null>(null);
	let pendingData = $state<Record<string, unknown> | null>(null);
	let isConfirming = $state(false);

	// Toast state
	let toasts = $state<{ id: number; message: string; type: 'success' | 'error' }[]>([]);
	let toastId = 0;

	// Derived values
	let taggedCount = $derived(fingerprintStats ? fingerprintStats.tagged : 0);
	let untaggedCount = $derived(fingerprintStats ? fingerprintStats.untagged : 0);
	let confirmedDogs = $derived(dogs.filter((d) => d.is_confirmed).length);

	// Load stats on mount
	$effect(() => {
		loadStats();
	});

	async function loadStats() {
		isLoadingStats = true;
		try {
			const [evidenceRes, fpRes, dogsRes] = await Promise.all([
				api.GET('/api/evidence/stats'),
				api.GET('/api/fingerprints/stats'),
				api.GET('/api/dogs')
			]);

			if (evidenceRes.data) {
				evidenceStats = evidenceRes.data;
			}
			if (fpRes.data) {
				fingerprintStats = fpRes.data;
			}
			if (dogsRes.data) {
				dogs = dogsRes.data;
			}
		} catch (error) {
			console.error('Failed to load stats:', error);
			showToast('Failed to load statistics', 'error');
		} finally {
			isLoadingStats = false;
		}
	}

	function formatDuration(seconds: number): string {
		if (seconds < 60) return `${Math.round(seconds)}s`;
		if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
		const hours = Math.floor(seconds / 3600);
		const mins = Math.round((seconds % 3600) / 60);
		return `${hours}h ${mins}m`;
	}

	function showToast(message: string, type: 'success' | 'error') {
		const id = ++toastId;
		toasts = [...toasts, { id, message, type }];

		// Auto-remove after 5 seconds
		setTimeout(() => {
			toasts = toasts.filter((t) => t.id !== id);
		}, 5000);
	}

	function openPurgeEvidenceModal() {
		if (!evidenceBeforeDate) {
			showToast('Please select a date', 'error');
			return;
		}

		pendingAction = 'evidence';
		pendingData = { before_date: evidenceBeforeDate + 'T23:59:59' };

		modalTitle = 'Purge Evidence Files';
		modalMessage = `This will permanently delete all evidence files recorded before ${evidenceBeforeDate}. This includes audio recordings (.wav), metadata (.json), and cached files (.opus).`;
		modalStats = [{ label: 'Delete before:', value: evidenceBeforeDate }];
		showModal = true;
	}

	function openPurgeFingerprintsModal() {
		if (!fingerprintsBeforeDate && !untaggedOnly) {
			showToast('Please select a date or check "untagged only"', 'error');
			return;
		}

		pendingAction = 'fingerprints';
		pendingData = {
			untagged_only: untaggedOnly,
			...(fingerprintsBeforeDate && { before_date: fingerprintsBeforeDate + 'T23:59:59' })
		};

		let message = 'This will permanently delete ';
		if (untaggedOnly && fingerprintsBeforeDate) {
			message += `untagged fingerprints before ${fingerprintsBeforeDate}.`;
		} else if (untaggedOnly) {
			message += 'all untagged fingerprints.';
		} else {
			message += `all fingerprints before ${fingerprintsBeforeDate}.`;
		}

		modalTitle = 'Purge Fingerprints';
		modalMessage = message;
		modalStats = [
			{ label: 'Untagged only:', value: untaggedOnly ? 'Yes' : 'No' },
			...(fingerprintsBeforeDate ? [{ label: 'Before date:', value: fingerprintsBeforeDate }] : [])
		];
		showModal = true;
	}

	function closeModal() {
		showModal = false;
		pendingAction = null;
		pendingData = null;
		isConfirming = false;
	}

	async function confirmAction() {
		if (!pendingAction || !pendingData) return;

		isConfirming = true;

		try {
			if (pendingAction === 'evidence') {
				const { data, error } = await api.POST('/api/maintenance/purge-evidence', {
					body: pendingData as { before_date: string }
				});

				if (error) {
					throw new Error(typeof error === 'string' ? error : 'Failed to purge evidence');
				}

				showToast(`Successfully deleted ${data?.deleted_count ?? 0} evidence files`, 'success');
			} else {
				const { data, error } = await api.POST('/api/maintenance/purge-fingerprints', {
					body: pendingData as { before_date?: string; untagged_only?: boolean }
				});

				if (error) {
					throw new Error(typeof error === 'string' ? error : 'Failed to purge fingerprints');
				}

				showToast(`Successfully deleted ${data?.deleted_count ?? 0} fingerprints`, 'success');
			}

			await loadStats();
		} catch (error) {
			console.error('Purge failed:', error);
			showToast(error instanceof Error ? error.message : 'Purge operation failed', 'error');
		} finally {
			closeModal();
		}
	}

	async function recalculateBarkCounts() {
		isRecalculating = true;

		try {
			const { data, error } = await api.POST('/api/maintenance/recalculate-bark-counts');

			if (error) {
				throw new Error(typeof error === 'string' ? error : 'Failed to recalculate');
			}

			showToast(data?.message ?? 'Bark counts recalculated successfully', 'success');
			await loadStats();
		} catch (error) {
			console.error('Recalculate failed:', error);
			showToast(error instanceof Error ? error.message : 'Recalculation failed', 'error');
		} finally {
			isRecalculating = false;
		}
	}
</script>

<svelte:head>
	<title>Settings & Maintenance - Woofalytics</title>
</svelte:head>

<div class="settings-page">
	<div class="settings-container">
		<div class="settings-content">
			<!-- Page Header -->
			<div class="page-header">
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<circle cx="12" cy="12" r="3" />
					<path
						d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"
					/>
				</svg>
				<div>
					<h1>Settings & Maintenance</h1>
					<p>Manage storage and cleanup old data</p>
				</div>
			</div>

			<!-- Stats Overview -->
			<div class="stats-overview">
				<div class="stat-card stat-card--evidence">
					<div class="stat-card-label">Evidence Files</div>
					<div class="stat-card-value">
						{#if isLoadingStats}
							--
						{:else}
							{evidenceStats?.total_files ?? 0}
						{/if}
					</div>
					<div class="stat-card-detail">
						{#if isLoadingStats}
							-- recorded
						{:else}
							{formatDuration(evidenceStats?.total_duration_seconds ?? 0)} recorded
						{/if}
					</div>
				</div>

				<div class="stat-card stat-card--fingerprints">
					<div class="stat-card-label">Fingerprints</div>
					<div class="stat-card-value">
						{#if isLoadingStats}
							--
						{:else}
							{fingerprintStats?.total ?? 0}
						{/if}
					</div>
					<div class="stat-card-detail">
						{#if isLoadingStats}
							-- tagged
						{:else}
							{taggedCount} tagged
						{/if}
					</div>
				</div>

				<div class="stat-card stat-card--untagged">
					<div class="stat-card-label">Untagged</div>
					<div class="stat-card-value">
						{#if isLoadingStats}
							--
						{:else}
							{untaggedCount}
						{/if}
					</div>
					<div class="stat-card-detail">awaiting classification</div>
				</div>

				<div class="stat-card stat-card--dogs">
					<div class="stat-card-label">Dogs</div>
					<div class="stat-card-value">
						{#if isLoadingStats}
							--
						{:else}
							{dogs.length}
						{/if}
					</div>
					<div class="stat-card-detail">
						{#if isLoadingStats}
							-- confirmed
						{:else}
							{confirmedDogs} confirmed
						{/if}
					</div>
				</div>
			</div>

			<!-- Purge Evidence Section -->
			<div class="maintenance-section maintenance-section--danger">
				<div class="section-header">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
						<polyline points="14 2 14 8 20 8" />
						<line x1="9" y1="15" x2="15" y2="15" />
					</svg>
					<h2>Purge Evidence Files</h2>
				</div>
				<div class="section-body">
					<p class="section-description">
						Remove old evidence recordings to free up disk space. Audio files (.wav) and their
						metadata (.json) will be permanently deleted. Cached transcoded files (.opus) are also
						removed.
					</p>
					<div class="form-row">
						<div class="form-group">
							<label class="form-label" for="evidenceBeforeDate">Delete evidence before</label>
							<input
								type="date"
								class="form-input"
								id="evidenceBeforeDate"
								bind:value={evidenceBeforeDate}
							/>
							<div class="form-hint">All recordings before this date will be deleted</div>
						</div>
						<button
							class="btn btn-danger"
							onclick={openPurgeEvidenceModal}
							disabled={isPurgingEvidence || !evidenceBeforeDate}
						>
							{#if isPurgingEvidence}
								<span class="spinner"></span>
								Purging...
							{:else}
								<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<polyline points="3 6 5 6 21 6" />
									<path
										d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"
									/>
								</svg>
								Purge Evidence
							{/if}
						</button>
					</div>
				</div>
			</div>

			<!-- Purge Fingerprints Section -->
			<div class="maintenance-section maintenance-section--danger">
				<div class="section-header">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path
							d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04l.054-.09A13.916 13.916 0 008 11a4 4 0 118 0c0 1.017-.07 2.019-.203 3m-2.118 6.844A21.88 21.88 0 0015.171 17m3.839 1.132c.645-2.266.99-4.659.99-7.132A8 8 0 008 4.07M3 15.364c.64-1.319 1-2.8 1-4.364 0-1.457.39-2.823 1.07-4"
						/>
					</svg>
					<h2>Purge Fingerprints</h2>
				</div>
				<div class="section-body">
					<p class="section-description">
						Remove bark fingerprints from the database. This affects the acoustic matching system.
						Fingerprints tagged to dogs contribute to their identification profile.
					</p>
					<div class="checkbox-group">
						<input type="checkbox" id="untaggedOnly" bind:checked={untaggedOnly} />
						<label for="untaggedOnly">Only purge untagged fingerprints (recommended)</label>
					</div>
					<div class="form-row">
						<div class="form-group">
							<label class="form-label" for="fingerprintsBeforeDate"
								>Delete fingerprints before (optional)</label
							>
							<input
								type="date"
								class="form-input"
								id="fingerprintsBeforeDate"
								bind:value={fingerprintsBeforeDate}
							/>
							<div class="form-hint">Leave empty to delete all untagged fingerprints</div>
						</div>
						<button
							class="btn btn-danger"
							onclick={openPurgeFingerprintsModal}
							disabled={isPurgingFingerprints || (!fingerprintsBeforeDate && !untaggedOnly)}
						>
							{#if isPurgingFingerprints}
								<span class="spinner"></span>
								Purging...
							{:else}
								<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<polyline points="3 6 5 6 21 6" />
									<path
										d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"
									/>
								</svg>
								Purge Fingerprints
							{/if}
						</button>
					</div>
				</div>
			</div>

			<!-- Data Sync Section -->
			<div class="maintenance-section">
				<div class="section-header">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<polyline points="23 4 23 10 17 10" />
						<polyline points="1 20 1 14 7 14" />
						<path
							d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"
						/>
					</svg>
					<h2>Data Sync</h2>
				</div>
				<div class="section-body">
					<p class="section-description">
						Synchronize cached statistics with actual database data. Use this if bark counts appear
						incorrect after purging fingerprints.
					</p>
					<div class="form-row">
						<button class="btn btn-secondary" onclick={recalculateBarkCounts} disabled={isRecalculating}>
							{#if isRecalculating}
								<span class="spinner"></span>
								Recalculating...
							{:else}
								<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<polyline points="23 4 23 10 17 10" />
									<path d="M20.49 15a9 9 0 11-2.12-9.36L23 10" />
								</svg>
								Recalculate Bark Counts
							{/if}
						</button>
					</div>
				</div>
			</div>
		</div>
	</div>

	<!-- Confirmation Modal -->
	{#if showModal}
		<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
		<div class="modal-overlay" onclick={closeModal}>
			<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
			<div class="modal" onclick={(e) => e.stopPropagation()}>
				<h3>
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path
							d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"
						/>
						<line x1="12" y1="9" x2="12" y2="13" />
						<line x1="12" y1="17" x2="12.01" y2="17" />
					</svg>
					<span>{modalTitle}</span>
				</h3>
				<p>{modalMessage}</p>
				<div class="modal-stats">
					{#each modalStats as stat}
						<div class="modal-stats-row">
							<span class="modal-stats-label">{stat.label}</span>
							<span class="modal-stats-value">{stat.value}</span>
						</div>
					{/each}
				</div>
				<div class="modal-actions">
					<button class="btn btn-cancel" onclick={closeModal} disabled={isConfirming}>
						Cancel
					</button>
					<button class="btn btn-danger" onclick={confirmAction} disabled={isConfirming}>
						{#if isConfirming}
							<span class="spinner"></span>
							Deleting...
						{:else}
							Delete Permanently
						{/if}
					</button>
				</div>
			</div>
		</div>
	{/if}

	<!-- Toast Notifications -->
	{#if toasts.length > 0}
		<div class="toast-container">
			{#each toasts as toast (toast.id)}
				<div class="toast toast-{toast.type}">
					{toast.message}
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	/* Settings Page Variables */
	.settings-page {
		--card-bg: rgba(22, 27, 34, 0.6);
		--danger-bg: rgba(239, 68, 68, 0.1);
		--danger-border: rgba(239, 68, 68, 0.3);
		--danger-text: #ef4444;
		--warning-bg: rgba(245, 158, 11, 0.1);
		--warning-border: rgba(245, 158, 11, 0.3);
		--warning-text: #f59e0b;
		--success-bg: rgba(16, 185, 129, 0.1);
		--success-border: rgba(16, 185, 129, 0.3);
		--success-text: #10b981;
	}

	.settings-container {
		max-width: 900px;
		margin: 0 auto;
		min-height: calc(100vh - 48px - 100px);
		display: flex;
		flex-direction: column;
	}

	.settings-content {
		flex: 1;
	}

	/* Page Header */
	.page-header {
		display: flex;
		align-items: center;
		gap: var(--space-md);
		margin-bottom: var(--space-xl);
	}

	.page-header svg {
		width: 32px;
		height: 32px;
		color: var(--accent-amber);
		flex-shrink: 0;
	}

	.page-header h1 {
		font-size: 1.75rem;
		font-weight: 700;
		color: var(--text-primary);
		margin: 0;
	}

	.page-header p {
		margin: 4px 0 0 0;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	/* Stats Overview */
	.stats-overview {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: var(--space-md);
		margin-bottom: var(--space-xl);
	}

	.stat-card {
		background: var(--card-bg);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-lg);
		padding: var(--space-lg);
		backdrop-filter: blur(20px);
	}

	.stat-card-label {
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-bottom: var(--space-xs);
	}

	.stat-card-value {
		font-size: 2rem;
		font-weight: 700;
		font-family: 'JetBrains Mono', monospace;
		color: var(--text-primary);
	}

	.stat-card-detail {
		font-size: 0.8rem;
		color: var(--text-muted);
		margin-top: var(--space-xs);
	}

	.stat-card--evidence .stat-card-value {
		color: var(--accent-teal);
	}
	.stat-card--fingerprints .stat-card-value {
		color: var(--accent-amber);
	}
	.stat-card--untagged .stat-card-value {
		color: var(--accent-coral);
	}
	.stat-card--dogs .stat-card-value {
		color: var(--accent-purple);
	}

	/* Maintenance Sections */
	.maintenance-section {
		background: var(--card-bg);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-lg);
		margin-bottom: var(--space-lg);
		backdrop-filter: blur(20px);
		overflow: hidden;
	}

	.maintenance-section--danger {
		border-color: var(--danger-border);
	}

	.section-header {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-md) var(--space-lg);
		border-bottom: 1px solid var(--border-muted);
		background: rgba(0, 0, 0, 0.2);
	}

	.section-header svg {
		width: 20px;
		height: 20px;
		color: var(--accent-amber);
		flex-shrink: 0;
	}

	.maintenance-section--danger .section-header svg {
		color: var(--danger-text);
	}

	.section-header h2 {
		font-size: 1rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.section-body {
		padding: var(--space-lg);
	}

	.section-description {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin-bottom: var(--space-lg);
		line-height: 1.6;
	}

	/* Form Controls */
	.form-group {
		margin-bottom: var(--space-lg);
	}

	.form-label {
		display: block;
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--text-secondary);
		margin-bottom: var(--space-xs);
	}

	.form-input {
		width: 100%;
		max-width: 300px;
		padding: var(--space-sm) var(--space-md);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
		color: var(--text-primary);
		font-size: 0.875rem;
		font-family: inherit;
	}

	.form-input:focus {
		outline: none;
		border-color: var(--accent-amber);
	}

	.form-input[type='date'] {
		color-scheme: dark;
	}

	.form-hint {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin-top: var(--space-xs);
	}

	.form-row {
		display: flex;
		align-items: flex-end;
		gap: var(--space-md);
		flex-wrap: wrap;
	}

	/* Checkbox */
	.checkbox-group {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		margin-bottom: var(--space-md);
	}

	.checkbox-group input[type='checkbox'] {
		width: 18px;
		height: 18px;
		accent-color: var(--accent-amber);
	}

	.checkbox-group label {
		font-size: 0.875rem;
		color: var(--text-secondary);
		cursor: pointer;
	}

	/* Buttons */
	.btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-sm) var(--space-lg);
		border: none;
		border-radius: var(--radius-md);
		font-size: 0.875rem;
		font-weight: 600;
		cursor: pointer;
		transition: all var(--transition-fast);
		white-space: nowrap;
	}

	.btn svg {
		width: 16px;
		height: 16px;
		flex-shrink: 0;
	}

	.btn-secondary {
		background: var(--bg-overlay);
		color: var(--text-secondary);
		border: 1px solid var(--border-default);
	}

	.btn-secondary:hover:not(:disabled) {
		background: var(--bg-surface);
		color: var(--text-primary);
	}

	.btn-danger {
		background: var(--danger-bg);
		color: var(--danger-text);
		border: 1px solid var(--danger-border);
	}

	.btn-danger:hover:not(:disabled) {
		background: rgba(239, 68, 68, 0.2);
	}

	.btn-cancel {
		background: var(--bg-overlay);
		color: var(--text-secondary);
		border: 1px solid var(--border-default);
	}

	.btn-cancel:hover:not(:disabled) {
		background: var(--bg-surface);
	}

	.btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	/* Modal */
	.modal-overlay {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		background: rgba(0, 0, 0, 0.8);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		backdrop-filter: blur(4px);
	}

	.modal {
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-lg);
		padding: var(--space-xl);
		max-width: 450px;
		width: 90%;
	}

	.modal h3 {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		font-size: 1.25rem;
		color: var(--danger-text);
		margin: 0 0 var(--space-md) 0;
	}

	.modal h3 svg {
		width: 24px;
		height: 24px;
		flex-shrink: 0;
	}

	.modal p {
		color: var(--text-secondary);
		line-height: 1.6;
		margin: 0 0 var(--space-lg) 0;
	}

	.modal-stats {
		background: var(--bg-overlay);
		border-radius: var(--radius-md);
		padding: var(--space-md);
		margin-bottom: var(--space-lg);
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.875rem;
	}

	.modal-stats-row {
		display: flex;
		justify-content: space-between;
		padding: var(--space-xs) 0;
	}

	.modal-stats-label {
		color: var(--text-muted);
	}

	.modal-stats-value {
		color: var(--text-primary);
		font-weight: 600;
	}

	.modal-actions {
		display: flex;
		gap: var(--space-md);
		justify-content: flex-end;
	}

	/* Toast Notifications */
	.toast-container {
		position: fixed;
		bottom: var(--space-lg);
		right: var(--space-lg);
		z-index: 3000;
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
	}

	.toast {
		padding: var(--space-md) var(--space-lg);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-lg);
		animation: slideIn 0.3s ease;
		font-size: 0.875rem;
	}

	.toast-success {
		border-color: var(--success-border);
		color: var(--success-text);
	}

	.toast-error {
		border-color: var(--danger-border);
		color: var(--danger-text);
	}

	@keyframes slideIn {
		from {
			transform: translateX(100%);
			opacity: 0;
		}
		to {
			transform: translateX(0);
			opacity: 1;
		}
	}

	/* Spinner */
	.spinner {
		width: 16px;
		height: 16px;
		border: 2px solid transparent;
		border-top-color: currentColor;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	/* Responsive */
	@media (max-width: 640px) {
		.stats-overview {
			grid-template-columns: repeat(2, 1fr);
		}

		.form-row {
			flex-direction: column;
			align-items: stretch;
		}

		.form-input {
			max-width: none;
		}

		.btn {
			justify-content: center;
		}

		.modal-actions {
			flex-direction: column-reverse;
		}

		.modal-actions .btn {
			width: 100%;
		}
	}
</style>
