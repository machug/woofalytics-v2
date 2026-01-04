<script lang="ts">
	import '../app.css';

	let { children } = $props();
</script>

<svelte:head>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
	<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
	<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🐕</text></svg>" />
</svelte:head>

<div class="app">
	<!-- Telemetry Strip / Navigation -->
	<nav class="telemetry-strip">
		<div class="telemetry-mission">
			<span class="mission-badge">WOOF-2</span>
			<span class="mission-callsign">Bark Detection System</span>
		</div>

		<div class="nav-links">
			<a href="/" class="nav-link">Dashboard</a>
			<a href="/dogs" class="nav-link">Dogs</a>
			<a href="/fingerprints" class="nav-link">Fingerprints</a>
			<a href="/settings" class="nav-link">Settings</a>
		</div>

		<div class="telemetry-clock">
			<span class="clock-label">MET</span>
			<span class="clock-value" id="mission-clock">00:00:00</span>
		</div>
	</nav>

	<main class="main-content">
		{@render children()}
	</main>

	<footer class="footer">
		<span>Woofalytics v2</span>
		<span class="footer-divider">|</span>
		<a href="https://github.com/machug/woofalytics-v2">GitHub</a>
	</footer>
</div>

<style>
	.nav-links {
		display: flex;
		gap: var(--space-lg);
	}

	.nav-link {
		font-size: 0.75rem;
		font-weight: 600;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--text-secondary);
		text-decoration: none;
		padding: var(--space-xs) var(--space-sm);
		border-radius: var(--radius-sm);
		transition: all var(--transition-fast);
	}

	.nav-link:hover {
		color: var(--accent-teal);
		background: var(--accent-teal-dim);
	}

	.nav-link:global(.active) {
		color: var(--accent-amber);
		background: var(--accent-amber-dim);
	}

	.main-content {
		flex: 1;
		padding: var(--space-lg);
		max-width: 1280px;
		margin: 0 auto;
		width: 100%;
	}

	@media (max-width: 768px) {
		.nav-links {
			gap: var(--space-sm);
		}

		.nav-link {
			font-size: 0.65rem;
			padding: var(--space-xs);
		}
	}
</style>
