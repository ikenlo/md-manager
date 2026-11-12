import { create } from 'zustand';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface ToastItem {
  id: string;
  type: ToastType;
  message: string;
  /** Set while the exit transition runs; the item is removed right after. */
  leaving?: boolean;
}

export interface ToastStore {
  toasts: ToastItem[];
  /**
   * Shows a toast. It disappears after `duration` ms (default 5000);
   * `duration <= 0` keeps it until closed manually. Returns the toast id.
   */
  addToast: (type: ToastType, message: string, duration?: number) => string;
  /** Starts the exit transition, then removes the toast. Safe to call twice. */
  removeToast: (id: string) => void;
}

/** Exit transition length; must match `duration-200` in Toast.tsx. */
export const TOAST_EXIT_MS = 200;
/** More than this many toasts on screen — the oldest one is dropped. */
const MAX_TOASTS = 5;

let seq = 0;
const timers = new Map<string, ReturnType<typeof setTimeout>>();

function clearTimer(id: string) {
  const t = timers.get(id);
  if (t !== undefined) clearTimeout(t);
  timers.delete(id);
}

export const useToastStore = create<ToastStore>((set, get) => ({
  toasts: [],

  addToast(type, message, duration = 5000) {
    const id = `toast-${++seq}`;
    set((s) => {
      const toasts = [...s.toasts, { id, type, message }];
      const visible = toasts.filter((t) => !t.leaving);
      if (visible.length > MAX_TOASTS) {
        const oldest = visible[0]!.id;
        clearTimer(oldest);
        return { toasts: toasts.filter((t) => t.id !== oldest) };
      }
      return { toasts };
    });
    if (duration > 0) timers.set(id, setTimeout(() => get().removeToast(id), duration));
    return id;
  },

  removeToast(id) {
    clearTimer(id);
    const item = get().toasts.find((t) => t.id === id);
    if (!item || item.leaving) return;
    set((s) => ({ toasts: s.toasts.map((t) => (t.id === id ? { ...t, leaving: true } : t)) }));
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), TOAST_EXIT_MS);
  },
}));

/**
 * Imperative helpers usable outside React (API callbacks, stores).
 *
 * @example
 * toast.success('Запис створено');
 * toast.error(err.message, 8000);
 */
export const toast = {
  success: (message: string, duration?: number) => useToastStore.getState().addToast('success', message, duration),
  error: (message: string, duration?: number) => useToastStore.getState().addToast('error', message, duration),
  warning: (message: string, duration?: number) => useToastStore.getState().addToast('warning', message, duration),
  info: (message: string, duration?: number) => useToastStore.getState().addToast('info', message, duration),
  dismiss: (id: string) => useToastStore.getState().removeToast(id),
};
