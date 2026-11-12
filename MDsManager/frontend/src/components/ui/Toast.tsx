import { AlertCircle, AlertTriangle, CheckCircle, Info, X, type LucideIcon } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useToastStore, type ToastItem, type ToastType } from '../../store/toast';
import { cn } from './cn';

const STYLE: Record<ToastType, { cls: string; Icon: LucideIcon }> = {
  // Connect .toast: темна плашка (bg ink, текст surface); .toast.err — червона
  success: { cls: 'bg-ink text-surface', Icon: CheckCircle },
  error: { cls: 'bg-danger text-white', Icon: AlertCircle },
  warning: { cls: 'bg-ink text-surface', Icon: AlertTriangle },
  info: { cls: 'bg-ink text-surface', Icon: Info },
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
        'pointer-events-auto flex w-full items-start gap-2.5 rounded-lg py-3 pl-4 pr-2 text-sm font-semibold shadow-lg',
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
        className="-my-1 shrink-0 rounded-sm p-1 opacity-70 transition hover:bg-[rgba(127,127,127,.2)] hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-current"
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
        'bottom-[calc(90px+env(safe-area-inset-bottom))] left-4 right-4 flex-col-reverse',
        'min-[601px]:bottom-auto min-[601px]:left-auto min-[601px]:right-5 min-[601px]:top-[18px] min-[601px]:w-[min(420px,calc(100vw-32px))] min-[601px]:flex-col',
      )}
    >
      {toasts.map((t) => (
        <ToastView key={t.id} item={t} onClose={() => removeToast(t.id)} />
      ))}
    </div>
  );
}
