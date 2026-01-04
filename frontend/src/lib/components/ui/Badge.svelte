<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		variant?: 'success' | 'warning' | 'danger' | 'info';
		children: Snippet;
	}

	let { variant = 'info', children }: Props = $props();

	const variantClass = $derived(`badge-${variant}`);
</script>

<span class="badge {variantClass}">
	{@render children()}
</span>
