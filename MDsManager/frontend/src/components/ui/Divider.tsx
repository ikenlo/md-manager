import type { ReactNode } from 'react';
import { cn } from './cn';

export interface DividerProps {
  /** Optional text in the middle: line — label — line. */
  label?: ReactNode;
  className?: string;
}

/**
 * Horizontal separator, optionally with a centred label (e.g. «або», a date in a chat).
 *
 * @example
 * <Divider />
 * <Divider label="Сьогодні" />
 */
export function Divider({ label, className }: DividerProps) {
  if (!label) {
    return <hr className={cn('my-0 h-px border-0 bg-line', className)} />;
  }
  return (
    <div role="separator" className={cn('flex items-center gap-3', className)}>
      <span className="h-px flex-1 bg-line" aria-hidden="true" />
      <span className="shrink-0 text-xs text-ink-3">{label}</span>
      <span className="h-px flex-1 bg-line" aria-hidden="true" />
    </div>
  );
}
