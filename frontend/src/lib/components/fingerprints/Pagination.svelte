<script lang="ts">
	/**
	 * Pagination - Page navigation controls
	 */

	interface Props {
		page: number;
		totalPages: number;
		totalItems?: number;
		pageSize?: number;
		onPageChange: (page: number) => void;
	}

	let { page, totalPages, totalItems, pageSize = 50, onPageChange }: Props = $props();

	const canGoPrevious = $derived(page > 1);
	const canGoNext = $derived(page < totalPages);

	const startItem = $derived((page - 1) * pageSize + 1);
	const endItem = $derived(Math.min(page * pageSize, totalItems ?? page * pageSize));

	const goToPage = (newPage: number) => {
		if (newPage >= 1 && newPage <= totalPages && newPage !== page) {
			onPageChange(newPage);
		}
	};

	const goPrevious = () => {
		if (canGoPrevious) {
			goToPage(page - 1);
		}
	};

	const goNext = () => {
		if (canGoNext) {
			goToPage(page + 1);
		}
	};
</script>

<div class="pagination">
	<div class="pagination-info">
		{#if totalItems !== undefined}
			Showing {startItem}-{endItem} of {totalItems}
		{:else}
			Page {page} of {totalPages}
		{/if}
	</div>

	<div class="pagination-controls">
		<button
			class="pagination-btn"
			onclick={goPrevious}
			disabled={!canGoPrevious}
			aria-label="Previous page"
		>
			<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<polyline points="15 18 9 12 15 6" />
			</svg>
		</button>

		<span class="pagination-page">
			Page {page} of {totalPages}
		</span>

		<button class="pagination-btn" onclick={goNext} disabled={!canGoNext} aria-label="Next page">
			<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<polyline points="9 18 15 12 9 6" />
			</svg>
		</button>
	</div>
</div>

<style>
	.pagination {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--space-md) var(--space-lg);
		border-top: 1px solid var(--border-muted);
		background: rgba(0, 0, 0, 0.1);
	}

	.pagination-info {
		font-size: 0.8rem;
		color: var(--text-muted);
	}

	.pagination-controls {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
	}

	.pagination-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 32px;
		height: 32px;
		background: var(--bg-overlay);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		color: var(--text-secondary);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.pagination-btn:hover:not(:disabled) {
		background: var(--accent-teal-dim);
		border-color: var(--accent-teal);
		color: var(--accent-teal);
	}

	.pagination-btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.pagination-btn svg {
		width: 16px;
		height: 16px;
	}

	.pagination-page {
		padding: var(--space-xs) var(--space-md);
		font-size: 0.8rem;
		color: var(--text-secondary);
		font-family: 'JetBrains Mono', monospace;
	}

	@media (max-width: 480px) {
		.pagination {
			flex-direction: column;
			gap: var(--space-sm);
		}
	}
</style>
