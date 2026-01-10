<script lang="ts">
  import { toast } from '$lib/stores/toast';
</script>

<div class="toast-container">
  {#each $toast as t (t.id)}
    <div class="toast toast-{t.type}" role="alert">
      <span>{t.message}</span>
      <button class="toast-dismiss" onclick={() => toast.dismiss(t.id)}>×</button>
    </div>
  {/each}
</div>

<style>
  .toast-container {
    position: fixed;
    bottom: 1rem;
    right: 1rem;
    z-index: 1000;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .toast {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.75rem 1rem;
    border-radius: var(--radius-md, 0.375rem);
    background: var(--bg-surface, #1e1e1e);
    border: 1px solid var(--border-default, #333);
    color: var(--text-primary, #fff);
    font-size: 0.875rem;
    min-width: 250px;
    max-width: 400px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    animation: slideIn 0.2s ease-out;
  }

  @keyframes slideIn {
    from {
      transform: translateX(100%);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }

  .toast-success {
    border-left: 3px solid #10b981;
  }

  .toast-error {
    border-left: 3px solid var(--accent-coral, #f87171);
  }

  .toast-info {
    border-left: 3px solid var(--accent-teal, #2dd4bf);
  }

  .toast-dismiss {
    background: none;
    border: none;
    color: inherit;
    cursor: pointer;
    padding: 0 0.5rem;
    font-size: 1.2rem;
    opacity: 0.6;
    transition: opacity 0.15s;
  }

  .toast-dismiss:hover {
    opacity: 1;
  }
</style>
