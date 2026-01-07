<script lang="ts">
	/**
	 * Reports Page - Bark statistics visualization and data export
	 * Features: date range picker, summary stats, trend charts, export modal
	 */

	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api/client';
	import type { DailySummary, MonthlySummary } from '$lib/api/types';

	import DateRangePicker from '$lib/components/reports/DateRangePicker.svelte';
	import SummaryStats from '$lib/components/reports/SummaryStats.svelte';
	import BarkTrendChart from '$lib/components/reports/BarkTrendChart.svelte';
	import HourlyBarChart from '$lib/components/reports/HourlyBarChart.svelte';
	import ExportPreviewModal from '$lib/components/reports/ExportPreviewModal.svelte';
	import AISummary from '$lib/components/reports/AISummary.svelte';

	// State
	let startDate = $state('');
	let endDate = $state('');
	let loading = $state(true);
	let error = $state<string | null>(null);
	let showExportModal = $state(false);

	// Data
	let dailySummary = $state<DailySummary | null>(null);
	let monthlySummary = $state<MonthlySummary | null>(null);
	let trendData = $state<{ date: string; count: number }[]>([]);

	// Initialize dates from URL or defaults
	function initializeDates() {
		const urlParams = $page.url.searchParams;
		const urlStart = urlParams.get('start');
		const urlEnd = urlParams.get('end');

		if (urlStart && urlEnd) {
			startDate = urlStart;
			endDate = urlEnd;
		} else {
			// Default to last 30 days
			const today = new Date();
			const thirtyDaysAgo = new Date(today);
			thirtyDaysAgo.setDate(today.getDate() - 30);

			startDate = thirtyDaysAgo.toISOString().split('T')[0];
			endDate = today.toISOString().split('T')[0];
		}
	}

	// Update URL with date range
	function updateUrl() {
		const url = new URL($page.url);
		url.searchParams.set('start', startDate);
		url.searchParams.set('end', endDate);
		goto(url.toString(), { replaceState: true, keepFocus: true });
	}

	// Fetch summary data
	async function fetchData() {
		loading = true;
		error = null;

		try {
			// Fetch daily summary for today (for hourly breakdown)
			const dailyResponse = await api.GET('/api/summary/daily', {
				params: { query: { date: endDate } }
			});

			if (dailyResponse.data) {
				dailySummary = dailyResponse.data;
			}

			// Fetch monthly summary for trend data
			const month = endDate.substring(0, 7); // YYYY-MM
			const monthlyResponse = await api.GET('/api/summary/monthly', {
				params: { query: { month } }
			});

			if (monthlyResponse.data) {
				monthlySummary = monthlyResponse.data;

				// Convert daily breakdown to trend data array
				const breakdown = monthlyResponse.data.daily_breakdown || {};
				trendData = Object.entries(breakdown)
					.map(([date, count]) => ({ date, count: count as number }))
					.filter((d) => {
						// Filter to selected date range
						return d.date >= startDate && d.date <= endDate;
					})
					.sort((a, b) => a.date.localeCompare(b.date));
			}
		} catch (err) {
			error = 'Failed to load report data. Please try again.';
			console.error('Failed to fetch report data:', err);
		} finally {
			loading = false;
		}
	}

	// Handle date range changes
	function handleRangeChange(start: string, end: string) {
		startDate = start;
		endDate = end;
		updateUrl();
		fetchData();
	}

	// Initialize on mount
	onMount(() => {
		initializeDates();
		fetchData();
	});

	// Derived stats for SummaryStats component
	const summaryData = $derived(
		monthlySummary
			? {
					total_barks: monthlySummary.total_barks,
					total_events: monthlySummary.total_events,
					total_duration_seconds: monthlySummary.total_duration_seconds,
					avg_confidence: monthlySummary.avg_confidence,
					peak_hour: dailySummary?.peak_hour ?? monthlySummary.peak_hour
				}
			: null
	);

	// Hourly data from daily summary
	const hourlyData = $derived(dailySummary?.hourly_breakdown ?? {});
</script>

<svelte:head>
	<title>Reports | Woofalytics</title>
</svelte:head>

<div class="reports-page">
	<header class="page-header">
		<div class="header-content">
			<h1 class="page-title">
				<span class="title-icon">📊</span>
				Bark Reports
			</h1>
			<p class="page-subtitle">Analyze bark patterns and export evidence data</p>
		</div>
		<button class="btn btn-teal" onclick={() => (showExportModal = true)}>
			<span class="btn-icon">📥</span>
			Export Data
		</button>
	</header>

	{#if error}
		<div class="error-banner">
			<span class="error-icon">⚠️</span>
			<span class="error-text">{error}</span>
			<button class="btn btn-ghost btn-sm" onclick={fetchData}>Retry</button>
		</div>
	{/if}

	<section class="date-section">
		<DateRangePicker bind:startDate bind:endDate onRangeChange={handleRangeChange} />
	</section>

	<section class="stats-section">
		<h2 class="section-title">Summary Statistics</h2>
		{#if monthlySummary}
			<p class="section-subtitle">
				Monthly totals for {new Date(endDate).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
			</p>
		{/if}
		<SummaryStats data={summaryData} {loading} />
	</section>

	<section class="ai-section">
		<AISummary date={endDate} />
	</section>

	<div class="charts-grid">
		<section class="chart-section">
			<h2 class="section-title">Bark Trend</h2>
			<p class="section-subtitle">Daily bark counts over selected period</p>
			<BarkTrendChart data={trendData} {loading} />
		</section>

		<section class="chart-section">
			<h2 class="section-title">Hourly Distribution</h2>
			<p class="section-subtitle">Bark counts by hour of day (latest day)</p>
			<HourlyBarChart data={hourlyData} {loading} />
		</section>
	</div>
</div>

<ExportPreviewModal bind:open={showExportModal} {startDate} {endDate} />

<style>
	.reports-page {
		display: flex;
		flex-direction: column;
		gap: var(--space-xl);
	}

	.page-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: var(--space-lg);
	}

	.header-content {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}

	.page-title {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		font-size: 1.5rem;
		font-weight: 700;
		color: var(--text-primary);
		margin: 0;
	}

	.title-icon {
		font-size: 1.75rem;
	}

	.page-subtitle {
		font-size: 0.9rem;
		color: var(--text-muted);
		margin: 0;
	}

	.btn-icon {
		margin-right: var(--space-xs);
	}

	.error-banner {
		display: flex;
		align-items: center;
		gap: var(--space-md);
		padding: var(--space-md) var(--space-lg);
		background: rgba(239, 68, 68, 0.1);
		border: 1px solid rgba(239, 68, 68, 0.3);
		border-radius: var(--radius-md);
	}

	.error-icon {
		font-size: 1.25rem;
	}

	.error-text {
		flex: 1;
		color: #f87171;
	}

	.date-section {
		margin-bottom: var(--space-sm);
	}

	.stats-section {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}

	.ai-section {
		margin-top: calc(-1 * var(--space-md));
	}

	.section-title {
		font-size: 1rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.section-subtitle {
		font-size: 0.8rem;
		color: var(--text-muted);
		margin: 0;
	}

	.charts-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
		gap: var(--space-lg);
	}

	.chart-section {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
	}

	@media (max-width: 768px) {
		.page-header {
			flex-direction: column;
			align-items: stretch;
		}

		.charts-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
