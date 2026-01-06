<script lang="ts">
	/**
	 * HourlyBarChart - Bar chart showing bark distribution by hour
	 * Uses Chart.js directly with Svelte 5
	 */

	import { onMount } from 'svelte';
	import {
		Chart,
		BarController,
		BarElement,
		LinearScale,
		CategoryScale,
		Tooltip
	} from 'chart.js';

	// Register Chart.js components
	Chart.register(BarController, BarElement, LinearScale, CategoryScale, Tooltip);

	interface Props {
		data: Record<number, number>; // hour (0-23) -> count
		loading?: boolean;
	}

	let { data, loading = false }: Props = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	// NASA theme colors
	const amberColor = '#f59e0b';
	const amberDim = 'rgba(245, 158, 11, 0.6)';
	const gridColor = 'rgba(255, 255, 255, 0.1)';
	const textColor = 'rgba(255, 255, 255, 0.7)';

	// Generate all 24 hours with counts
	function getHourlyData(): { labels: string[]; values: number[] } {
		const labels: string[] = [];
		const values: number[] = [];

		for (let i = 0; i < 24; i++) {
			// Format as 12-hour time
			const suffix = i >= 12 ? 'p' : 'a';
			const hour = i % 12 || 12;
			labels.push(`${hour}${suffix}`);
			values.push(data[i] ?? 0);
		}

		return { labels, values };
	}

	function createChart() {
		if (!canvas) return;

		const ctx = canvas.getContext('2d');
		if (!ctx) return;

		const { labels, values } = getHourlyData();

		chart = new Chart(ctx, {
			type: 'bar',
			data: {
				labels,
				datasets: [
					{
						label: 'Barks',
						data: values,
						backgroundColor: values.map((v, i) => {
							// Highlight peak hour
							const maxVal = Math.max(...values);
							return v === maxVal && v > 0 ? amberColor : amberDim;
						}),
						borderColor: amberColor,
						borderWidth: 1,
						borderRadius: 4
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				plugins: {
					tooltip: {
						backgroundColor: 'rgba(15, 23, 42, 0.9)',
						borderColor: amberColor,
						borderWidth: 1,
						titleColor: '#fff',
						bodyColor: amberColor,
						padding: 12,
						displayColors: false,
						callbacks: {
							title: (items) => {
								const idx = items[0]?.dataIndex ?? 0;
								const suffix = idx >= 12 ? 'PM' : 'AM';
								const hour = idx % 12 || 12;
								return `${hour}:00 ${suffix}`;
							},
							label: (item) => `${item.raw} barks`
						}
					}
				},
				scales: {
					x: {
						grid: {
							display: false
						},
						ticks: {
							color: textColor,
							font: {
								family: "'JetBrains Mono', monospace",
								size: 9
							}
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

		const { labels, values } = getHourlyData();
		chart.data.labels = labels;
		chart.data.datasets[0].data = values;
		// Update bar colors to highlight peak
		const maxVal = Math.max(...values);
		chart.data.datasets[0].backgroundColor = values.map((v) =>
			v === maxVal && v > 0 ? amberColor : amberDim
		);
		chart.update();
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

	// Check if there's any data
	const hasData = $derived(Object.values(data).some((v) => v > 0));
</script>

<div class="chart-container" class:loading>
	<canvas bind:this={canvas}></canvas>
	{#if loading}
		<div class="loading-overlay">
			<span class="loading-text">Loading chart...</span>
		</div>
	{/if}
	{#if !loading && !hasData}
		<div class="empty-state">
			<span class="empty-icon">📊</span>
			<span class="empty-text">No hourly data available</span>
		</div>
	{/if}
</div>

<style>
	.chart-container {
		position: relative;
		height: 250px;
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
