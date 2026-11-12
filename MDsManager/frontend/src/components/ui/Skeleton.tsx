import type { CSSProperties, HTMLAttributes } from 'react';
import { cn } from './cn';

export interface SkeletonProps extends HTMLAttributes<HTMLSpanElement> {
  /** CSS width; number = px. Defaults to `'100%'` (`'2.5rem'` for `circle`). */
  width?: number | string;
  /** CSS height; number = px. Defaults to `'1rem'`. For `circle` it always equals `width`. */
  height?: number | string;
  /** `text` — rounded line, `rect` — block (cards, images), `circle` — avatar. */
  variant?: 'text' | 'circle' | 'rect';
}

const toCss = (v: number | string) => (typeof v === 'number' ? `${v}px` : v);

/**
 * Loading placeholder. Hidden from screen readers — announce loading
 * on the container instead (e.g. `aria-busy="true"`).
 *
 * @example
 * <Skeleton variant="circle" width={40} />
 * <Skeleton width="60%" />
 * <Skeleton variant="rect" height={58} />
 */
export function Skeleton({ width, height = '1rem', variant = 'text', className, style, ...rest }: SkeletonProps) {
  const isCircle = variant === 'circle';
  const w = toCss(width ?? (isCircle ? '2.5rem' : '100%'));
  const size: CSSProperties = isCircle ? { width: w, height: w } : { width: w, height: toCss(height) };
  return (
    <span
      aria-hidden="true"
      style={{ ...size, ...style }}
      className={cn(
        'block shrink-0 animate-pulse bg-surface-2 motion-reduce:animate-none',
        variant === 'text' && 'rounded-xs',
        variant === 'rect' && 'rounded-lg',
        isCircle && 'rounded-full',
        className,
      )}
      {...rest}
    />
  );
}
