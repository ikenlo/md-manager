import { AlertCircle, AlertTriangle, CheckCircle, Info, X, type LucideIcon } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useToastStore, type ToastItem, type ToastType } from '../../store/toast';
import { cn } from './cn';

const STYLE: Record<ToastType, { cls: string; Icon: LucideIcon }> = {
  success: { cls: 'bg-ok', Icon: CheckCircle },
  error: { cls: 'bg-danger', Icon: AlertCircle },
  warning: { cls: 'bg-warn', Icon: AlertTriangle },
  info: { cls: 'bg-info', Icon: Info },
};

function ToastView({ item, onClose }: { item: ToastItem; onClose: () => void }) {
  const [entered, setEntered] = useState(false);
  useEffect(() => {
    const raf = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  const { cls, Icon } = STYLE[item.type];
  const shown = entered && !item.leaving;
  const urgent = item.type === 'error' || item.type === 'warning';

  return (
    <div
      role={urgent ? 'alert' : 'status'}
      className={cn(
        'pointer-events-auto flex w-full items-start gap-2.5 rounded-lg py-3 pl-4 pr-2 text-sm font-semibold text-white shadow-lg',
        'transition duration-200 ease-ease motion-reduce:transition-none',
        shown ? 'translate-y-0 opacity-100' : '-translate-y-2 opacity-0',
        cls,
      )}
    >
      <Icon size={18} className="mt-px shrink-0" aria-hidden="true" />
      <p className="min-w-0 flex-1 break-words leading-snug">{item.message}</p>
      <button
        type="button"
        onClick={onClose}
        aria-label="Закрити повідомлення"
        className="-my-1 shrink-0 rounded-sm p-1 text-white/80 transition hover:bg-white/15 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60"
      >
        <X size={16} />
      </button>
    </div>
  );
}

/**
 * Renders all toasts from `useToastStore`. Mount once near the app root;
 * show toasts anywhere with `toast.success('…')` etc.
 *
 * Desktop (≥900px): top-right. Mobile: top-centre, full width minus gutters.
 */
export function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts);
  const removeToast = useToastStore((s) => s.removeToast);
  if (!toasts.length) return null;
  return (
    <div
      aria-live="polite"
      className={cn(
        'pointer-events-none fixed z-[100] flex flex-col gap-2',
        'left-1/2 top-4 w-[calc(100vw-32px)] max-w-[420px] -translate-x-1/2',
        'min-[900px]:left-auto min-[900px]:right-4 min-[900px]:w-[380px] min-[900px]:translate-x-0',
      )}
    >
      {toasts.map((t) => (
        <ToastView key={t.id} item={t} onClose={() => removeToast(t.id)} />
      ))}
    </div>
  );
}
