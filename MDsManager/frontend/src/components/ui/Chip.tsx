import type { HTMLAttributes } from 'react';
import { cn } from './cn';

export type ChipVariant =
  | 'new'
  | 'in_progress'
  | 'ordered'
  | 'lost'
  | 'info'
  | 'ok'
  | 'warn'
  | 'danger'
  | 'prog'
  | 'muted'
  | 'gold';
export type ChipSize = 'sm' | 'md';

export interface ChipProps extends HTMLAttributes<HTMLSpanElement> {
  /** Colour scheme. `new | in_progress | ordered | lost` match `DialogueStatus`, so `<Chip variant={d.status}>` works. */
  variant?: ChipVariant;
  /** Defaults to `md`. */
  size?: ChipSize;
  /** Coloured dot before the text (MDS Connect `.chip::before`). Defaults to true; `false` = `.chip.plain`. */
  dot?: boolean;
}

// Семантика як у Connect (.st-*): нове — info, в роботі — prog, записано — ok, втрачено — muted
const VARIANTS: Record<ChipVariant, string> = {
  new: 'bg-info-bg text-info',
  in_progress: 'bg-prog-bg text-prog',
  ordered: 'bg-ok-bg text-ok',
  lost: 'bg-muted-bg text-ink-3',
  info: 'bg-info-bg text-info',
  ok: 'bg-ok-bg text-ok',
  warn: 'bg-warn-bg text-warn',
  danger: 'bg-danger-bg text-danger',
  prog: 'bg-prog-bg text-prog',
  muted: 'bg-muted-bg text-ink-2',
  gold: 'bg-gold-tint text-gold',
};

const SIZES: Record<ChipSize, string> = {
  sm: 'min-h-5 px-2 text-[10.5px] gap-1',
  md: 'min-h-[22px] px-[9px] text-xs gap-1.5',
};

/** Status pill (MDS Connect `.chip` / `.st-*`). */
export function Chip({ variant = 'muted', size = 'md', dot = true, className, children, ...rest }: ChipProps) {
  return (
    <span
      className={cn(
        'inline-flex max-w-full items-center whitespace-nowrap rounded-pill font-bold leading-none',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {dot && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-current opacity-[.85]" aria-hidden="true" />}
      {children}
    </span>
  );
}
