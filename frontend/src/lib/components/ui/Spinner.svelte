<script lang="ts">
	interface Props {
		size?: 'sm' | 'md' | 'lg';
	}

	let { size = 'md' }: Props = $props();
</script>

<span class="spinner spinner-{size}" role="status" aria-label="Loading"></span>

<style>
	.spinner-sm {
		width: 14px;
		height: 14px;
		border-width: 2px;
	}

	.spinner-md {
		width: 20px;
		height: 20px;
		border-width: 2px;
	}

	.spinner-lg {
		width: 32px;
		height: 32px;
		border-width: 3px;
	}
</style>
