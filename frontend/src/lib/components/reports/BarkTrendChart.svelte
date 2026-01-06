<script lang="ts">
	/**
	 * BarkTrendChart - Line chart showing bark trends over time
	 * Uses Chart.js directly with Svelte 5
	 */

	import { onMount } from 'svelte';
	import {
		Chart,
		LineController,
		LineElement,
		PointElement,
		LinearScale,
		CategoryScale,
		Tooltip,
		Filler
	} from 'chart.js';

	// Register Chart.js components
	Chart.register(
		LineController,
		LineElement,
		PointElement,
		LinearScale,
		CategoryScale,
		Tooltip,
		Filler
	);

	interface Props {
		data: { date: string; count: number }[];
		loading?: boolean;
	}

	let { data, loading = false }: Props = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	// NASA theme colors
	const tealColor = '#14b8a6';
	const tealDim = 'rgba(20, 184, 166, 0.2)';
	const gridColor = 'rgba(255, 255, 255, 0.1)';
	const textColor = 'rgba(255, 255, 255, 0.7)';

	function createChart() {
		if (!canvas) return;

		const ctx = canvas.getContext('2d');
		if (!ctx) return;

		chart = new Chart(ctx, {
			type: 'line',
			data: {
				labels: data.map((d) => formatDateLabel(d.date)),
				datasets: [
					{
						label: 'Barks',
						data: data.map((d) => d.count),
						borderColor: tealColor,
						backgroundColor: tealDim,
						borderWidth: 2,
						fill: true,
						tension: 0.3,
						pointRadius: 4,
						pointBackgroundColor: tealColor,
						pointBorderColor: '#0f172a',
						pointBorderWidth: 2,
						pointHoverRadius: 6
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				interaction: {
					intersect: false,
					mode: 'index'
				},
				plugins: {
					tooltip: {
						backgroundColor: 'rgba(15, 23, 42, 0.9)',
						borderColor: tealColor,
						borderWidth: 1,
						titleColor: '#fff',
						bodyColor: tealColor,
						padding: 12,
						displayColors: false,
						callbacks: {
							title: (items) => items[0]?.label ?? '',
							label: (item) => `${item.raw} barks`
						}
					}
				},
				scales: {
					x: {
						grid: {
							color: gridColor
						},
						ticks: {
							color: textColor,
							font: {
								family: "'JetBrains Mono', monospace",
								size: 10
							},
							maxRotation: 45
						}
					},
					y: {
						beginAtZero: true,
						grid: {
							color: gridColor
						},
						ticks: {
							color: textColor,
							font: {
								family: "'JetBrains Mono', monospace",
								size: 10
							},
							stepSize: 1
						}
					}
				}
			}
		});
	}

	function updateChart() {
		if (!chart) return;

		chart.data.labels = data.map((d) => formatDateLabel(d.date));
		chart.data.datasets[0].data = data.map((d) => d.count);
		chart.update();
	}

	function formatDateLabel(dateStr: string): string {
		const date = new Date(dateStr);
		return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
	}

	onMount(() => {
		createChart();
		return () => chart?.destroy();
	});

	// Update chart when data changes
	$effect(() => {
		if (chart && data) {
			updateChart();
		}
	});
</script>

<div class="chart-container" class:loading>
	<canvas bind:this={canvas}></canvas>
	{#if loading}
		<div class="loading-overlay">
			<span class="loading-text">Loading chart...</span>
		</div>
	{/if}
	{#if !loading && data.length === 0}
		<div class="empty-state">
			<span class="empty-icon">📉</span>
			<span class="empty-text">No data for selected period</span>
		</div>
	{/if}
</div>

<style>
	.chart-container {
		position: relative;
		height: 300px;
		padding: var(--space-md);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
	}

	.chart-container.loading canvas {
		opacity: 0.3;
	}

	.loading-overlay,
	.empty-state {
		position: absolute;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-sm);
	}

	.loading-text,
	.empty-text {
		font-size: 0.85rem;
		color: var(--text-muted);
	}

	.empty-icon {
		font-size: 2rem;
	}
</style>
