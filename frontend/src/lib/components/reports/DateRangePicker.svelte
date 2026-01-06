<script lang="ts">
	/**
	 * DateRangePicker - Date range selection with presets for reports
	 * Supports preset ranges and custom date selection
	 */

	type DatePreset = 'today' | 'week' | 'month' | 'last30' | 'custom';

	interface Props {
		startDate: string;
		endDate: string;
		onRangeChange: (start: string, end: string) => void;
	}

	let { startDate = $bindable(), endDate = $bindable(), onRangeChange }: Props = $props();

	let activePreset = $state<DatePreset>('last30');

	// Compute dates for presets
	function getPresetDates(preset: DatePreset): { start: string; end: string } {
		const today = new Date();
		const formatDate = (d: Date) => d.toISOString().split('T')[0];

		switch (preset) {
			case 'today': {
				const todayStr = formatDate(today);
				return { start: todayStr, end: todayStr };
			}
			case 'week': {
				const weekStart = new Date(today);
				weekStart.setDate(today.getDate() - today.getDay());
				return { start: formatDate(weekStart), end: formatDate(today) };
			}
			case 'month': {
				const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);
				return { start: formatDate(monthStart), end: formatDate(today) };
			}
			case 'last30': {
				const thirtyDaysAgo = new Date(today);
				thirtyDaysAgo.setDate(today.getDate() - 30);
				return { start: formatDate(thirtyDaysAgo), end: formatDate(today) };
			}
			case 'custom':
			default:
				return { start: startDate, end: endDate };
		}
	}

	function handlePresetClick(preset: DatePreset) {
		activePreset = preset;
		if (preset !== 'custom') {
			const { start, end } = getPresetDates(preset);
			startDate = start;
			endDate = end;
			onRangeChange(start, end);
		}
	}

	function handleStartDateChange(event: Event) {
		const target = event.target as HTMLInputElement;
		startDate = target.value;
		activePreset = 'custom';
		onRangeChange(startDate, endDate);
	}

	function handleEndDateChange(event: Event) {
		const target = event.target as HTMLInputElement;
		endDate = target.value;
		activePreset = 'custom';
		onRangeChange(startDate, endDate);
	}

	// Format date range for display
	const dateRangeDisplay = $derived(() => {
		if (!startDate || !endDate) return 'Select dates';
		const start = new Date(startDate);
		const end = new Date(endDate);
		const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' };
		if (startDate === endDate) {
			return start.toLocaleDateString('en-US', { ...opts, year: 'numeric' });
		}
		return `${start.toLocaleDateString('en-US', opts)} - ${end.toLocaleDateString('en-US', { ...opts, year: 'numeric' })}`;
	});

	const presets: { key: DatePreset; label: string }[] = [
		{ key: 'today', label: 'Today' },
		{ key: 'week', label: 'This Week' },
		{ key: 'month', label: 'This Month' },
		{ key: 'last30', label: 'Last 30 Days' }
	];
</script>

<div class="date-range-picker">
	<div class="preset-buttons">
		{#each presets as preset (preset.key)}
			<button
				class="preset-btn"
				class:active={activePreset === preset.key}
				onclick={() => handlePresetClick(preset.key)}
			>
				{preset.label}
			</button>
		{/each}
	</div>

	<div class="custom-range">
		<div class="date-input-group">
			<label class="date-label" for="start-date">From</label>
			<input
				type="date"
				id="start-date"
				class="date-input"
				value={startDate}
				onchange={handleStartDateChange}
			/>
		</div>
		<span class="date-separator">—</span>
		<div class="date-input-group">
			<label class="date-label" for="end-date">To</label>
			<input
				type="date"
				id="end-date"
				class="date-input"
				value={endDate}
				onchange={handleEndDateChange}
			/>
		</div>
	</div>

	<div class="range-display">
		<span class="range-icon">📅</span>
		<span class="range-text">{dateRangeDisplay()}</span>
	</div>
</div>

<style>
	.date-range-picker {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
		padding: var(--space-lg);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
	}

	.preset-buttons {
		display: flex;
		gap: var(--space-sm);
		flex-wrap: wrap;
	}

	.preset-btn {
		padding: var(--space-xs) var(--space-md);
		background: var(--bg-overlay);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		color: var(--text-secondary);
		font-size: 0.8rem;
		font-weight: 500;
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.preset-btn:hover {
		background: var(--accent-teal-dim);
		border-color: var(--accent-teal);
		color: var(--accent-teal);
	}

	.preset-btn.active {
		background: var(--accent-teal);
		border-color: var(--accent-teal);
		color: var(--bg-base);
	}

	.custom-range {
		display: flex;
		align-items: flex-end;
		gap: var(--space-sm);
	}

	.date-input-group {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}

	.date-label {
		font-size: 0.7rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.date-input {
		padding: var(--space-xs) var(--space-sm);
		background: var(--bg-overlay);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		color: var(--text-primary);
		font-size: 0.85rem;
		font-family: 'JetBrains Mono', monospace;
	}

	.date-input:focus {
		outline: none;
		border-color: var(--accent-teal);
	}

	.date-input::-webkit-calendar-picker-indicator {
		filter: invert(0.7);
	}

	.date-separator {
		color: var(--text-muted);
		padding-bottom: var(--space-xs);
	}

	.range-display {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-sm) var(--space-md);
		background: var(--accent-teal-dim);
		border-radius: var(--radius-sm);
		border-left: 3px solid var(--accent-teal);
	}

	.range-icon {
		font-size: 1rem;
	}

	.range-text {
		font-size: 0.85rem;
		font-weight: 500;
		color: var(--text-primary);
	}

	@media (max-width: 640px) {
		.custom-range {
			flex-direction: column;
			align-items: stretch;
		}

		.date-separator {
			display: none;
		}

		.date-input {
			width: 100%;
		}
	}
</style>
