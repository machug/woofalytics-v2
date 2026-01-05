<script lang="ts">
	/**
	 * FingerprintTable - Sortable data table for fingerprints
	 * Features sortable columns, expandable rows with audio playback, confidence badges
	 */

	import type { Fingerprint } from '$lib/api/types';
	import AudioPlayer from './AudioPlayer.svelte';

	interface Props {
		fingerprints: Fingerprint[];
		sortBy: string;
		sortOrder: 'asc' | 'desc';
		onSort: (column: string) => void;
		isLoading?: boolean;
	}

	let { fingerprints, sortBy, sortOrder, onSort, isLoading = false }: Props = $props();

	// Track which row is expanded for audio playback
	let expandedRow: string | null = $state(null);

	// Column definitions
	const columns = [
		{ key: 'timestamp', label: 'Timestamp', sortable: true },
		{ key: 'dog_name', label: 'Dog', sortable: true },
		{ key: 'detection_probability', label: 'Confidence', sortable: true },
		{ key: 'duration_ms', label: 'Duration', sortable: true },
		{ key: 'pitch_hz', label: 'Pitch', sortable: true },
		{ key: 'actions', label: 'Actions', sortable: false }
	];

	const handleSort = (column: string) => {
		const col = columns.find((c) => c.key === column);
		if (col?.sortable) {
			onSort(column);
		}
	};

	const toggleRow = (id: string) => {
		expandedRow = expandedRow === id ? null : id;
	};

	// Get confidence badge class
	const getConfidenceClass = (confidence: number): string => {
		if (confidence >= 0.8) return 'high';
		if (confidence >= 0.5) return 'medium';
		return 'low';
	};

	// Format timestamp for display
	const formatTimestamp = (timestamp: string): string => {
		const date = new Date(timestamp);
		return date.toLocaleString('en-US', {
			month: 'short',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit',
			second: '2-digit',
			hour12: true
		});
	};

	// Format duration from ms to readable
	const formatDuration = (ms: number): string => {
		if (!ms) return '--';
		return (ms / 1000).toFixed(2) + 's';
	};

	// Format pitch
	const formatPitch = (hz: number | null): string => {
		if (hz === null || hz === undefined) return '--';
		return Math.round(hz) + ' Hz';
	};

	// Get sort icon
	const getSortIcon = (column: string): string => {
		if (sortBy !== column) return '';
		return sortOrder === 'asc' ? '\u25B2' : '\u25BC';
	};
</script>

<div class="fp-table-container">
	{#if isLoading}
		<div class="loading-state">
			<div class="spinner"></div>
			<span>Loading fingerprints...</span>
		</div>
	{:else if fingerprints.length === 0}
		<div class="empty-state">
			<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
				<path
					d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04l.054-.09A13.916 13.916 0 008 11a4 4 0 118 0c0 1.017-.07 2.019-.203 3m-2.118 6.844A21.88 21.88 0 0015.171 17m3.839 1.132c.645-2.266.99-4.659.99-7.132A8 8 0 008 4.07M3 15.364c.64-1.319 1-2.8 1-4.364 0-1.457.39-2.823 1.07-4"
				/>
			</svg>
			<span>No fingerprints found.</span>
			<span class="empty-state-hint">Try adjusting your filters.</span>
		</div>
	{:else}
		<table class="fp-table">
			<thead>
				<tr>
					{#each columns as col (col.key)}
						<th
							class:sortable={col.sortable}
							class:sorted={sortBy === col.key}
							onclick={() => handleSort(col.key)}
						>
							{col.label}
							{#if col.sortable}
								<span class="sort-icon">{getSortIcon(col.key)}</span>
							{/if}
						</th>
					{/each}
				</tr>
			</thead>
			<tbody>
				{#each fingerprints as fp (fp.id)}
					<tr class:expanded={expandedRow === fp.id}>
						<td class="mono">{formatTimestamp(fp.timestamp)}</td>
						<td>
							{#if fp.dog_name}
								<span class="dog-tag">{fp.dog_name}</span>
							{:else}
								<span class="dog-tag dog-tag--unknown">Untagged</span>
							{/if}
						</td>
						<td>
							<span class="confidence-badge confidence-badge--{getConfidenceClass(fp.detection_probability)}">
								{Math.round(fp.detection_probability * 100)}%
							</span>
						</td>
						<td class="mono">{formatDuration(fp.duration_ms)}</td>
						<td class="mono">{formatPitch(fp.pitch_hz)}</td>
						<td>
							{#if fp.evidence_filename}
								<button
									class="action-btn action-btn--play"
									class:active={expandedRow === fp.id}
									onclick={() => toggleRow(fp.id)}
									title={expandedRow === fp.id ? 'Close player' : 'Play recording'}
								>
									{#if expandedRow === fp.id}
										<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
											<line x1="18" y1="6" x2="6" y2="18" />
											<line x1="6" y1="6" x2="18" y2="18" />
										</svg>
									{:else}
										<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
											<polygon points="5 3 19 12 5 21 5 3" />
										</svg>
									{/if}
								</button>
							{:else}
								<span class="no-audio">--</span>
							{/if}
						</td>
					</tr>
					{#if expandedRow === fp.id && fp.evidence_filename}
						<tr class="expanded-row">
							<td colspan="6">
								<div class="audio-row">
									<AudioPlayer src={fp.evidence_filename} onClose={() => (expandedRow = null)} />
								</div>
							</td>
						</tr>
					{/if}
				{/each}
			</tbody>
		</table>
	{/if}
</div>

<style>
	.fp-table-container {
		overflow-x: auto;
	}

	.fp-table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.85rem;
	}

	.fp-table th {
		text-align: left;
		padding: var(--space-sm) var(--space-md);
		font-size: 0.7rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
		border-bottom: 1px solid var(--border-default);
		white-space: nowrap;
		user-select: none;
		transition: color var(--transition-fast);
	}

	.fp-table th.sortable {
		cursor: pointer;
	}

	.fp-table th.sortable:hover {
		color: var(--text-secondary);
	}

	.fp-table th.sorted {
		color: var(--accent-teal);
	}

	.sort-icon {
		display: inline-block;
		margin-left: 4px;
		opacity: 0.5;
		font-size: 0.6rem;
	}

	.fp-table th.sorted .sort-icon {
		opacity: 1;
	}

	.fp-table td {
		padding: var(--space-sm) var(--space-md);
		border-bottom: 1px solid var(--border-muted);
		color: var(--text-secondary);
		white-space: nowrap;
	}

	.fp-table tbody tr {
		transition: background var(--transition-fast);
	}

	.fp-table tbody tr:hover {
		background: var(--bg-overlay);
	}

	.fp-table tbody tr.expanded {
		background: var(--bg-overlay);
	}

	.expanded-row {
		background: var(--bg-surface) !important;
	}

	.expanded-row td {
		padding: var(--space-md);
		border-bottom: 1px solid var(--border-default);
	}

	.audio-row {
		display: flex;
		justify-content: flex-start;
	}

	.mono {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.8rem;
	}

	/* Dog Tag */
	.dog-tag {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		padding: 2px 10px;
		background: var(--accent-amber-dim);
		color: var(--accent-amber);
		border-radius: var(--radius-full);
		font-size: 0.75rem;
		font-weight: 600;
	}

	.dog-tag--unknown {
		background: rgba(100, 116, 139, 0.12);
		color: #64748b;
	}

	/* Confidence Badge */
	.confidence-badge {
		display: inline-flex;
		padding: 2px 8px;
		border-radius: var(--radius-full);
		font-size: 0.75rem;
		font-weight: 600;
		font-family: 'JetBrains Mono', monospace;
	}

	.confidence-badge--high {
		background: rgba(16, 185, 129, 0.12);
		color: #10b981;
	}

	.confidence-badge--medium {
		background: rgba(245, 158, 11, 0.12);
		color: #f59e0b;
	}

	.confidence-badge--low {
		background: rgba(100, 116, 139, 0.12);
		color: #64748b;
	}

	/* Action Buttons */
	.action-btn {
		display: inline-flex;
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

	.action-btn:hover {
		background: var(--bg-overlay);
		color: var(--text-primary);
		border-color: var(--accent-teal);
	}

	.action-btn--play:hover,
	.action-btn--play.active {
		border-color: var(--accent-amber);
		color: var(--accent-amber);
	}

	.action-btn--play.active {
		background: var(--accent-amber-dim);
	}

	.action-btn svg {
		width: 14px;
		height: 14px;
	}

	.no-audio {
		color: var(--text-muted);
		font-size: 0.8rem;
	}

	/* Loading State */
	.loading-state {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-sm);
		padding: var(--space-xl);
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.spinner {
		width: 16px;
		height: 16px;
		border: 2px solid var(--border-default);
		border-top-color: var(--accent-teal);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	/* Empty State */
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

	.empty-state-hint {
		font-size: 0.8rem;
		margin-top: var(--space-xs);
		opacity: 0.7;
	}

	@media (max-width: 768px) {
		.fp-table {
			font-size: 0.8rem;
		}

		.fp-table th,
		.fp-table td {
			padding: var(--space-xs) var(--space-sm);
		}
	}
</style>
