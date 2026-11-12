import type { HTMLAttributes } from 'react';
import { cn } from './cn';

export type BadgeVariant = 'brand' | 'danger';

export interface BadgeProps extends Omit<HTMLAttributes<HTMLSpanElement>, 'children'> {
  /** Number to show. Nothing is rendered when it is 0 or negative. */
  count: number;
  /** Above this the badge shows `${max}+`. Defaults to 99. */
  max?: number;
  /** Defaults to `brand`. */
  variant?: BadgeVariant;
}

const VARIANTS: Record<BadgeVariant, string> = {
  brand: 'bg-brand text-white dark:bg-gold dark:text-[#17120a]',
  danger: 'bg-danger text-white',
};

/**
 * Numeric counter, e.g. unread messages.
 *
 * @example
 * <Badge count={dialogue.unread_count} aria-label={`${dialogue.unread_count} непрочитаних`} />
 */
export function Badge({ count, max = 99, variant = 'brand', className, ...rest }: BadgeProps) {
  if (!Number.isFinite(count) || count <= 0) return null;
  const text = count > max ? `${max}+` : String(Math.floor(count));
  return (
    <span
      className={cn(
        'inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-pill px-1.5',
        'text-2xs font-bold leading-none tabular-nums',
        VARIANTS[variant],
        className,
      )}
      {...rest}
    >
      {text}
    </span>
  );
}
