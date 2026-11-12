import type { ReactNode } from 'react';
import { cn } from './cn';

export interface SegOption<T extends string> {
  value: T;
  label: ReactNode;
  icon?: ReactNode;
  /** Tooltip. */
  title?: string;
  /** Small number after the label (e.g. a filter count). */
  count?: number;
}

export interface SegProps<T extends string> {
  options: Array<SegOption<T>>;
  value: T;
  onChange: (value: T) => void;
  /** Accessible name of the group. */
  'aria-label': string;
  className?: string;
}

/**
 * Segmented control (MDS Connect `.seg`): grey track, the selected segment is a white "card".
 * Radio semantics (`role="radiogroup"` / `role="radio"`). Scrolls horizontally if it does not fit.
 */
export function Seg<T extends string>({ options, value, onChange, className, ...rest }: SegProps<T>) {
  return (
    <div
      role="radiogroup"
      aria-label={rest['aria-label']}
      className={cn(
        'inline-flex max-w-full gap-0.5 overflow-x-auto rounded-md bg-surface-3 p-[3px] [scrollbar-width:none]',
        className,
      )}
    >
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            title={o.title}
            onClick={() => onChange(o.value)}
            className={cn(
              'inline-flex min-h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-sm px-3 text-[13px] font-semibold',
              'transition duration-1 active:scale-[.97] focus-visible:outline-none focus-visible:shadow-ring',
              on
                ? 'bg-surface text-ink shadow-[0_1px_2px_rgba(20,30,25,.1),0_0_0_1px_rgba(20,30,25,.04)]'
                : 'text-ink-2 hover:bg-[rgba(127,127,127,.08)] hover:text-ink',
            )}
          >
            {o.icon}
            {o.label}
            {o.count !== undefined && <span className={cn('tabular-nums', on ? 'text-ink-3' : 'text-ink-3/80')}>{o.count}</span>}
          </button>
        );
      })}
    </div>
  );
}
