<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		variant?: 'amber' | 'teal' | 'coral' | 'outline';
		size?: 'sm' | 'md';
		disabled?: boolean;
		loading?: boolean;
		type?: 'button' | 'submit' | 'reset';
		onclick?: (e: MouseEvent) => void;
		children: Snippet;
	}

	let {
		variant = 'amber',
		size = 'md',
		disabled = false,
		loading = false,
		type = 'button',
		onclick,
		children
	}: Props = $props();

	const variantClass = $derived(variant === 'outline' ? 'btn-outline' : `btn-${variant}`);
	const sizeClass = $derived(size === 'sm' ? 'btn-sm' : '');
</script>

<button
	{type}
	class="btn {variantClass} {sizeClass}"
	disabled={disabled || loading}
	{onclick}
>
	{#if loading}
		<span class="spinner spinner-button"></span>
	{/if}
	{@render children()}
</button>

<style>
	.spinner-button {
		width: 14px;
		height: 14px;
		border-width: 2px;
	}

	.btn-sm .spinner-button {
		width: 12px;
		height: 12px;
	}
</style>
