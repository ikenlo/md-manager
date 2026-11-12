import type { CSSProperties, HTMLAttributes } from 'react';
import { cn } from './cn';

export interface SkeletonProps extends HTMLAttributes<HTMLSpanElement> {
  /** CSS width; number = px. Defaults to `'100%'` (`'2.5rem'` for `circle`). */
  width?: number | string;
  /** CSS height; number = px. Defaults to `'1rem'` (58px for `rect`, like Connect). For `circle` it equals `width`. */
  height?: number | string;
  /** `text` — rounded line, `rect` — block (cards, rows), `circle` — avatar. */
  variant?: 'text' | 'circle' | 'rect';
}

const toCss = (v: number | string) => (typeof v === 'number' ? `${v}px` : v);

/**
 * Loading placeholder with the MDS Connect shimmer (`.skeleton i`). Hidden from screen readers —
 * announce loading on the container instead (`aria-busy="true"`).
 */
export function Skeleton({ width, height, variant = 'text', className, style, ...rest }: SkeletonProps) {
  const isCircle = variant === 'circle';
  const w = toCss(width ?? (isCircle ? '2.5rem' : '100%'));
  const h = toCss(height ?? (variant === 'rect' ? 58 : '1rem'));
  const size: CSSProperties = isCircle ? { width: w, height: w } : { width: w, height: h };
  return (
    <span
      aria-hidden="true"
      style={{ ...size, ...style }}
      className={cn(
        'block shrink-0 animate-shimmer bg-[length:200%_100%]',
        'bg-[linear-gradient(90deg,rgb(var(--surface-2))_25%,rgb(var(--surface-3))_50%,rgb(var(--surface-2))_75%)]',
        variant === 'text' && 'rounded-xs',
        variant === 'rect' && 'rounded-lg',
        isCircle && 'rounded-full',
        className,
      )}
      {...rest}
    />
  );
}
