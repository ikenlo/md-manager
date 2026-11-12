import type { HTMLAttributes } from 'react';
import { cn } from './cn';

export type ChipVariant = 'new' | 'in_progress' | 'ordered' | 'lost' | 'info';
export type ChipSize = 'sm' | 'md';

export interface ChipProps extends HTMLAttributes<HTMLSpanElement> {
  /** Colour scheme. The first four match `DialogueStatus`, so `<Chip variant={d.status}>` works. */
  variant?: ChipVariant;
  /** Defaults to `md`. */
  size?: ChipSize;
  /** Coloured dot before the text (MDS Connect `.chip::before`). */
  dot?: boolean;
}

const VARIANTS: Record<ChipVariant, string> = {
  new: 'bg-surface-2 text-ink-2',
  in_progress: 'bg-gold-tint text-gold',
  ordered: 'bg-ok/10 text-ok',
  lost: 'bg-danger/10 text-danger',
  info: 'bg-info/10 text-info',
};

const SIZES: Record<ChipSize, string> = {
  sm: 'text-[10px] px-2 py-0.5 gap-1',
  md: 'text-xs px-2.5 py-1 gap-1.5',
};

/**
 * Status pill (MDS Connect `.chip`).
 *
 * @example
 * <Chip variant={dialogue.status} dot>{STATUS_LABEL[dialogue.status]}</Chip>
 */
export function Chip({ variant = 'new', size = 'md', dot = false, className, children, ...rest }: ChipProps) {
  return (
    <span
      className={cn(
        'inline-flex max-w-full items-center whitespace-nowrap rounded-pill font-semibold leading-4',
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
