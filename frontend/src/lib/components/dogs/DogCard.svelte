<script lang="ts">
	import type { Dog } from '$lib/api/types';

	interface Props {
		dog: Dog;
		onEdit: (dog: Dog) => void;
		onDelete: (dog: Dog) => void;
		onViewBarks: (dog: Dog) => void;
		onToggleConfirm: (dog: Dog) => void;
	}

	let { dog, onEdit, onDelete, onViewBarks, onToggleConfirm }: Props = $props();

	let menuOpen = $state(false);

	function toggleMenu(event: MouseEvent) {
		event.stopPropagation();
		menuOpen = !menuOpen;
	}

	function closeMenu() {
		menuOpen = false;
	}

	function handleEdit() {
		closeMenu();
		onEdit(dog);
	}

	function handleDelete() {
		closeMenu();
		onDelete(dog);
	}

	function handleViewBarks() {
		closeMenu();
		onViewBarks(dog);
	}

	function handleToggleConfirm() {
		closeMenu();
		onToggleConfirm(dog);
	}

	function formatRelativeTime(dateStr: string): string {
		const date = new Date(dateStr);
		const now = new Date();
		const diff = now.getTime() - date.getTime();
		const minutes = Math.floor(diff / 60000);
		const hours = Math.floor(diff / 3600000);
		const days = Math.floor(diff / 86400000);

		if (minutes < 1) return 'Just now';
		if (minutes < 60) return `${minutes}m ago`;
		if (hours < 24) return `${hours}h ago`;
		if (days < 7) return `${days}d ago`;
		return date.toLocaleDateString();
	}
</script>

<svelte:window onclick={closeMenu} />

<div class="dog-card">
	<div class="dog-avatar">
		{dog.emoji || '🐕'}
	</div>

	<div class="dog-content">
		<div class="dog-header">
			<span class="dog-name">{dog.name}</span>
			{#if dog.is_confirmed}
				<span class="status-chip status-chip--active">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
						<polyline points="22 4 12 14.01 9 11.01" />
					</svg>
					Confirmed
				</span>
			{:else}
				<span class="status-chip status-chip--pending">Unconfirmed</span>
			{/if}
		</div>

		{#if dog.notes}
			<div class="dog-notes">{dog.notes}</div>
		{/if}

		<div class="dog-stats">
			<div class="dog-stat">
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<path d="M11 5L6 9H2v6h4l5 4V5z" />
				</svg>
				<strong>{dog.bark_count}</strong> barks
			</div>
			<div class="dog-stat">
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<circle cx="12" cy="12" r="10" />
					<polyline points="12 6 12 12 16 14" />
				</svg>
				{formatRelativeTime(dog.updated_at)}
			</div>
		</div>
	</div>

	<div class="dog-actions">
		{#if dog.is_confirmed}
			<button class="btn-action btn-action--teal" onclick={handleViewBarks}>
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<path d="M11 5L6 9H2v6h4l5 4V5z" />
				</svg>
				Barks ({dog.bark_count})
			</button>
		{:else}
			<button class="btn-action btn-action--primary" onclick={handleToggleConfirm}>
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
					<polyline points="22 4 12 14.01 9 11.01" />
				</svg>
				Confirm
			</button>
			<button class="btn-action" onclick={handleViewBarks}>
				Barks
			</button>
		{/if}

		<div class="actions-menu" class:open={menuOpen}>
			<button class="btn-action" onclick={toggleMenu} aria-label="More actions">
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<circle cx="12" cy="12" r="1" />
					<circle cx="12" cy="5" r="1" />
					<circle cx="12" cy="19" r="1" />
				</svg>
			</button>
			<div class="actions-dropdown">
				<button class="dropdown-item" onclick={handleEdit}>
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
						<path d="M18.5 2.5a2.12 2.12 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
					</svg>
					Edit Profile
				</button>
				<button class="dropdown-item" onclick={handleToggleConfirm}>
					{#if dog.is_confirmed}
						<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<circle cx="12" cy="12" r="10" />
							<line x1="15" y1="9" x2="9" y2="15" />
							<line x1="9" y1="9" x2="15" y2="15" />
						</svg>
						Remove Confirmation
					{:else}
						<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
							<polyline points="22 4 12 14.01 9 11.01" />
						</svg>
						Confirm Dog
					{/if}
				</button>
				<div class="dropdown-divider"></div>
				<button class="dropdown-item dropdown-item--danger" onclick={handleDelete}>
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<polyline points="3 6 5 6 21 6" />
						<path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
					</svg>
					Delete Dog
				</button>
			</div>
		</div>
	</div>
</div>

<style>
	.dog-card {
		display: flex;
		align-items: center;
		gap: var(--space-md);
		padding: var(--space-md);
		background: transparent;
		border-radius: var(--radius-md);
		border: 1px solid transparent;
		transition: all var(--transition-fast);
		margin-bottom: var(--space-xs);
	}

	.dog-card:hover {
		background: rgba(28, 33, 40, 0.8);
		border-color: var(--border-default);
	}

	.dog-avatar {
		width: 44px;
		height: 44px;
		border-radius: 50%;
		background: linear-gradient(135deg, var(--accent-amber-dim), rgba(245, 158, 11, 0.25));
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1.25rem;
		flex-shrink: 0;
		border: 2px solid var(--accent-amber-dim);
	}

	.dog-content {
		flex: 1;
		min-width: 0;
	}

	.dog-header {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		margin-bottom: 2px;
	}

	.dog-name {
		font-size: 0.95rem;
		font-weight: 600;
		color: var(--text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.dog-notes {
		font-size: 0.75rem;
		color: var(--text-muted);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.status-chip {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		padding: 2px 8px;
		font-size: 0.625rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		border-radius: var(--radius-full);
		border: 1px solid;
		white-space: nowrap;
	}

	.status-chip svg {
		width: 10px;
		height: 10px;
	}

	.status-chip--active {
		background: rgba(16, 185, 129, 0.12);
		border-color: rgba(16, 185, 129, 0.25);
		color: #10b981;
	}

	.status-chip--pending {
		background: rgba(100, 116, 139, 0.12);
		border-color: rgba(100, 116, 139, 0.25);
		color: #64748b;
	}

	.dog-stats {
		display: flex;
		align-items: center;
		gap: var(--space-md);
		margin-top: 4px;
	}

	.dog-stat {
		display: flex;
		align-items: center;
		gap: 4px;
		font-size: 0.7rem;
		color: var(--text-muted);
	}

	.dog-stat strong {
		font-weight: 600;
		color: var(--text-secondary);
		font-family: 'JetBrains Mono', monospace;
	}

	.dog-stat svg {
		width: 12px;
		height: 12px;
		opacity: 0.6;
	}

	.dog-actions {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		flex-shrink: 0;
	}

	.btn-action {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 4px;
		padding: var(--space-xs) var(--space-sm);
		font-size: 0.7rem;
		font-weight: 600;
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		background: transparent;
		color: var(--text-secondary);
		cursor: pointer;
		transition: all var(--transition-fast);
		white-space: nowrap;
	}

	.btn-action svg {
		width: 12px;
		height: 12px;
	}

	.btn-action:hover {
		background: var(--bg-overlay);
		color: var(--text-primary);
		border-color: var(--text-muted);
	}

	.btn-action--primary {
		background: var(--accent-amber);
		border-color: var(--accent-amber);
		color: var(--bg-base);
	}

	.btn-action--primary:hover {
		background: #fbbf24;
		border-color: #fbbf24;
	}

	.btn-action--teal {
		background: var(--accent-teal-dim);
		border-color: var(--accent-teal);
		color: var(--accent-teal);
	}

	.btn-action--teal:hover {
		background: var(--accent-teal);
		color: var(--bg-base);
	}

	.actions-menu {
		position: relative;
	}

	.actions-dropdown {
		position: absolute;
		top: 100%;
		right: 0;
		min-width: 160px;
		margin-top: 4px;
		padding: var(--space-xs);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-lg);
		z-index: 100;
		opacity: 0;
		visibility: hidden;
		transform: translateY(-8px);
		transition: all var(--transition-fast);
	}

	.actions-menu.open .actions-dropdown {
		opacity: 1;
		visibility: visible;
		transform: translateY(0);
	}

	.dropdown-item {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		width: 100%;
		padding: var(--space-sm) var(--space-md);
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-secondary);
		background: transparent;
		border: none;
		border-radius: var(--radius-sm);
		cursor: pointer;
		transition: all var(--transition-fast);
		text-align: left;
	}

	.dropdown-item svg {
		width: 14px;
		height: 14px;
	}

	.dropdown-item:hover {
		background: var(--bg-overlay);
		color: var(--text-primary);
	}

	.dropdown-item--danger:hover {
		background: var(--accent-coral-dim);
		color: var(--accent-coral);
	}

	.dropdown-divider {
		height: 1px;
		background: var(--border-muted);
		margin: var(--space-xs) 0;
	}

	@media (max-width: 768px) {
		.dog-card {
			flex-wrap: wrap;
		}

		.dog-actions {
			width: 100%;
			justify-content: flex-start;
			margin-top: var(--space-sm);
			padding-top: var(--space-sm);
			border-top: 1px solid var(--border-muted);
		}
	}
</style>
