<script lang="ts">
	/**
	 * FilterPanel - Filters for fingerprints table
	 * Supports dog selection, date range, tagged/untagged toggle, min confidence
	 */

	import type { Dog } from '$lib/api/types';

	export interface Filters {
		dog_id: string;
		start_date: string;
		end_date: string;
		tagged: boolean | null;
		min_confidence: number;
	}

	interface Props {
		filters: Filters;
		dogs: Dog[];
		onApply: (filters: Filters) => void;
		onReset: () => void;
	}

	let { filters = $bindable(), dogs, onApply, onReset }: Props = $props();

	// Local filter state for debounced updates
	let localFilters = $state<Filters>({ ...filters });

	// Sync local state when filters prop changes
	$effect(() => {
		localFilters = { ...filters };
	});

	// Tagged toggle state
	type TaggedFilter = 'all' | 'tagged' | 'untagged';
	let taggedState = $derived<TaggedFilter>(
		localFilters.tagged === null ? 'all' : localFilters.tagged ? 'tagged' : 'untagged'
	);

	const handleDogChange = (event: Event) => {
		const target = event.target as HTMLSelectElement;
		localFilters.dog_id = target.value;
	};

	const handleStartDateChange = (event: Event) => {
		const target = event.target as HTMLInputElement;
		localFilters.start_date = target.value;
	};

	const handleEndDateChange = (event: Event) => {
		const target = event.target as HTMLInputElement;
		localFilters.end_date = target.value;
	};

	const handleTaggedToggle = (value: TaggedFilter) => {
		if (value === 'all') {
			localFilters.tagged = null;
		} else if (value === 'tagged') {
			localFilters.tagged = true;
		} else {
			localFilters.tagged = false;
		}
	};

	const handleConfidenceChange = (event: Event) => {
		const target = event.target as HTMLInputElement;
		localFilters.min_confidence = parseFloat(target.value);
	};

	const handleApply = () => {
		filters = { ...localFilters };
		onApply(localFilters);
	};

	const handleReset = () => {
		localFilters = {
			dog_id: '',
			start_date: '',
			end_date: '',
			tagged: null,
			min_confidence: 0
		};
		filters = { ...localFilters };
		onReset();
	};

	// Format confidence for display
	const confidencePercent = $derived(Math.round(localFilters.min_confidence * 100));
</script>

<div class="filter-panel">
	<div class="filters-bar">
		<!-- Dog Filter -->
		<div class="filter-group">
			<label class="filter-label" for="filter-dog">Dog</label>
			<select
				id="filter-dog"
				class="filter-select"
				value={localFilters.dog_id}
				onchange={handleDogChange}
			>
				<option value="">All Dogs</option>
				{#each dogs as dog (dog.id)}
					<option value={dog.id}>{dog.emoji} {dog.name}</option>
				{/each}
			</select>
		</div>

		<!-- Tagged/Untagged Toggle -->
		<div class="filter-group" role="group" aria-labelledby="status-label">
			<span id="status-label" class="filter-label">Status</span>
			<div class="filter-toggle">
				<button
					class="filter-toggle-btn"
					class:active={taggedState === 'all'}
					onclick={() => handleTaggedToggle('all')}
				>
					All
				</button>
				<button
					class="filter-toggle-btn"
					class:active={taggedState === 'tagged'}
					onclick={() => handleTaggedToggle('tagged')}
				>
					Tagged
				</button>
				<button
					class="filter-toggle-btn"
					class:active={taggedState === 'untagged'}
					onclick={() => handleTaggedToggle('untagged')}
				>
					Untagged
				</button>
			</div>
		</div>

		<!-- Date Range -->
		<div class="filter-group">
			<label class="filter-label" for="filter-date-start">From</label>
			<input
				type="date"
				id="filter-date-start"
				class="filter-input"
				value={localFilters.start_date}
				onchange={handleStartDateChange}
			/>
		</div>

		<div class="filter-group">
			<label class="filter-label" for="filter-date-end">To</label>
			<input
				type="date"
				id="filter-date-end"
				class="filter-input"
				value={localFilters.end_date}
				onchange={handleEndDateChange}
			/>
		</div>

		<!-- Min Confidence Slider -->
		<div class="filter-group filter-group--slider">
			<label class="filter-label" for="filter-confidence">
				Min Confidence: <span class="confidence-value">{confidencePercent}%</span>
			</label>
			<input
				type="range"
				id="filter-confidence"
				class="filter-slider"
				min="0"
				max="1"
				step="0.05"
				value={localFilters.min_confidence}
				oninput={handleConfidenceChange}
			/>
		</div>

		<!-- Action Buttons -->
		<div class="filter-actions">
			<button class="btn btn-teal btn-sm" onclick={handleApply}>Apply</button>
			<button class="btn-filter-reset" onclick={handleReset}>Reset</button>
		</div>
	</div>
</div>

<style>
	.filter-panel {
		padding: var(--space-md) var(--space-lg);
		border-bottom: 1px solid var(--border-muted);
		background: rgba(0, 0, 0, 0.2);
	}

	.filters-bar {
		display: flex;
		align-items: flex-end;
		gap: var(--space-md);
		flex-wrap: wrap;
	}

	.filter-group {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}

	.filter-group--slider {
		min-width: 140px;
	}

	.filter-label {
		font-size: 0.7rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.confidence-value {
		color: var(--accent-teal);
		font-family: 'JetBrains Mono', monospace;
	}

	.filter-select {
		padding: var(--space-xs) var(--space-sm);
		background: var(--bg-overlay);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		color: var(--text-primary);
		font-size: 0.8rem;
		cursor: pointer;
		min-width: 140px;
	}

	.filter-select:focus {
		outline: none;
		border-color: var(--accent-teal);
	}

	.filter-input {
		padding: var(--space-xs) var(--space-sm);
		background: var(--bg-overlay);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		color: var(--text-primary);
		font-size: 0.8rem;
		width: 140px;
	}

	.filter-input:focus {
		outline: none;
		border-color: var(--accent-teal);
	}

	/* Date picker icon color fix for dark theme */
	.filter-input::-webkit-calendar-picker-indicator {
		filter: invert(0.7);
	}

	.filter-slider {
		-webkit-appearance: none;
		appearance: none;
		width: 100%;
		height: 6px;
		background: var(--border-default);
		border-radius: 3px;
		outline: none;
		cursor: pointer;
	}

	.filter-slider::-webkit-slider-thumb {
		-webkit-appearance: none;
		appearance: none;
		width: 16px;
		height: 16px;
		background: var(--accent-teal);
		border-radius: 50%;
		cursor: pointer;
		transition: transform var(--transition-fast);
	}

	.filter-slider::-webkit-slider-thumb:hover {
		transform: scale(1.1);
	}

	.filter-slider::-moz-range-thumb {
		width: 16px;
		height: 16px;
		background: var(--accent-teal);
		border-radius: 50%;
		border: none;
		cursor: pointer;
	}

	.filter-toggle {
		display: flex;
		background: var(--bg-overlay);
		border-radius: var(--radius-sm);
		overflow: hidden;
		border: 1px solid var(--border-default);
	}

	.filter-toggle-btn {
		padding: var(--space-xs) var(--space-md);
		background: transparent;
		border: none;
		color: var(--text-muted);
		font-size: 0.75rem;
		font-weight: 500;
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.filter-toggle-btn:hover {
		color: var(--text-secondary);
	}

	.filter-toggle-btn.active {
		background: var(--accent-teal);
		color: var(--bg-base);
	}

	.filter-actions {
		display: flex;
		gap: var(--space-sm);
		align-items: center;
		margin-left: auto;
	}

	.btn-filter-reset {
		padding: var(--space-xs) var(--space-sm);
		background: transparent;
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		color: var(--text-muted);
		font-size: 0.75rem;
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.btn-filter-reset:hover {
		background: var(--bg-overlay);
		color: var(--text-primary);
	}

	@media (max-width: 768px) {
		.filters-bar {
			flex-direction: column;
			align-items: stretch;
		}

		.filter-group {
			width: 100%;
		}

		.filter-select,
		.filter-input {
			width: 100%;
		}

		.filter-actions {
			margin-left: 0;
			justify-content: flex-end;
		}
	}
</style>
