import { writable } from 'svelte/store';

interface Toast {
  id: string;
  type: 'success' | 'error' | 'info';
  message: string;
}

function createToastStore() {
  const { subscribe, update } = writable<Toast[]>([]);

  return {
    subscribe,
    show: (type: Toast['type'], message: string, duration = 4000) => {
      const id = crypto.randomUUID();
      update(toasts => [...toasts, { id, type, message }]);
      if (duration > 0) {
        setTimeout(() => {
          update(toasts => toasts.filter(t => t.id !== id));
        }, duration);
      }
    },
    dismiss: (id: string) => update(toasts => toasts.filter(t => t.id !== id))
  };
}

export const toast = createToastStore();
