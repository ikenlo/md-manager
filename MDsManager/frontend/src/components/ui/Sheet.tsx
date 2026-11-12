import { X } from 'lucide-react';
import { useEffect, useId, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { cn } from './cn';

export interface SheetProps {
  /** Controlled visibility. */
  open: boolean;
  /** Called on overlay click, Escape or the close button. */
  onClose: () => void;
  /** `right` drawer on desktop (becomes a bottom sheet below 900px) or always `bottom`. */
  side?: 'right' | 'bottom';
  /** Heading in the title bar; also the dialog's accessible name. */
  title?: ReactNode;
  children?: ReactNode;
  /** Sticky footer (actions). */
  footer?: ReactNode;
  /** Drawer width on desktop for `side="right"`. Number = px. Defaults to 400. */
  width?: number | string;
  /** Extra classes for the panel. */
  className?: string;
}

const ANIM_MS = 200;
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Side drawer / bottom sheet — the MDS Connect replacement for modals (`openSheet`).
 *
 * - Overlay click and Escape call `onClose`.
 * - Focus moves to the first focusable element inside, Tab is trapped,
 *   and focus returns to the element that opened the sheet.
 * - Body scroll is locked while open.
 * - Below 900px a right drawer turns into a bottom sheet (max 90vh).
 *
 * @example
 * <Sheet open={open} onClose={() => setOpen(false)} title="Новий запис"
 *        footer={<Button fullWidth onClick={save}>Зберегти</Button>}>
 *   …form…
 * </Sheet>
 */
export function Sheet({
  open,
  onClose,
  side = 'right',
  title,
  children,
  footer,
  width = 400,
  className,
}: SheetProps) {
  const [mounted, setMounted] = useState(open);
  const [visible, setVisible] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const titleId = useId();

  // Mount → next frame visible (enter transition); close → transition out → unmount.
  useEffect(() => {
    if (open) {
      setMounted(true);
      const raf = requestAnimationFrame(() => requestAnimationFrame(() => setVisible(true)));
      return () => cancelAnimationFrame(raf);
    }
    setVisible(false);
    const t = setTimeout(() => setMounted(false), ANIM_MS);
    return () => clearTimeout(t);
  }, [open]);

  // Focus, Escape, Tab trap, scroll lock — only while open.
  useEffect(() => {
    if (!open || !mounted) return;
    const trigger = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    const focusables = () => (panel ? Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)) : []);

    const contentFirst = focusables().find((el) => !el.dataset.sheetClose);
    (contentFirst ?? focusables()[0] ?? panel)?.focus({ preventScroll: true });

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (e.key !== 'Tab') return;
      const list = focusables();
      if (!list.length) {
        e.preventDefault();
        return;
      }
      const first = list[0]!;
      const last = list[list.length - 1]!;
      const active = document.activeElement;
      if (e.shiftKey && (active === first || !panel?.contains(active))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (active === last || !panel?.contains(active))) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKey);

    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
      if (trigger && document.contains(trigger)) trigger.focus({ preventScroll: true });
    };
  }, [open, mounted]);

  if (!mounted) return null;

  const isRight = side === 'right';
  const style = { '--sheet-w': typeof width === 'number' ? `${width}px` : width } as CSSProperties;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-end min-[900px]:items-stretch">
      <div
        aria-hidden="true"
        onClick={onClose}
        className={cn(
          'absolute inset-0 bg-[rgba(15,22,19,.38)] backdrop-blur-[2px] transition-opacity duration-200 ease-out',
          visible ? 'opacity-100' : 'opacity-0',
        )}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        tabIndex={-1}
        style={style}
        className={cn(
          'relative flex flex-col bg-surface shadow-lg outline-none',
          'transition-transform duration-200 ease-out motion-reduce:transition-none',
          // mobile (<900px): always a bottom sheet
          'max-h-[90vh] w-full overscroll-contain rounded-t-xl pb-[env(safe-area-inset-bottom)]',
          visible ? 'translate-y-0' : 'translate-y-full',
          isRight
            ? cn(
                'min-[900px]:h-full min-[900px]:max-h-none min-[900px]:w-[var(--sheet-w)] min-[900px]:max-w-full',
                'min-[900px]:rounded-none min-[900px]:pb-0 min-[900px]:translate-y-0',
                visible ? 'min-[900px]:translate-x-0' : 'min-[900px]:translate-x-full',
              )
            : 'min-[900px]:mx-auto min-[900px]:self-end min-[900px]:max-w-[720px]',
          className,
        )}
      >
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-line px-6 py-4">
          <h2 id={titleId} className="m-0 min-w-0 truncate text-lg font-bold text-ink">
            {title}
          </h2>
          <button
            type="button"
            data-sheet-close="true"
            onClick={onClose}
            aria-label="Закрити"
            className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-sm text-ink-3 transition hover:bg-surface-3 hover:text-ink focus-visible:outline-none focus-visible:shadow-ring"
          >
            <X size={18} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">{children}</div>
        {footer && <div className="sticky bottom-0 shrink-0 border-t border-line bg-surface px-6 py-4">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}
