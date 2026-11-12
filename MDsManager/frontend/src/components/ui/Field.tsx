import type { HTMLAttributes, ReactNode } from 'react';
import { cn } from './cn';

export interface FieldProps extends Omit<HTMLAttributes<HTMLDivElement>, 'children'> {
  /** Text above the control. */
  label?: ReactNode;
  /** `id` of the wrapped control — links the `<label>` to it. */
  htmlFor?: string;
  /** Adds a red asterisk after the label. */
  required?: boolean;
  /** Error text below the control; takes priority over `helper`. */
  error?: ReactNode;
  /** Hint text below the control. */
  helper?: ReactNode;
  /** Id for the error/helper text, so the control can reference it via `aria-describedby`. */
  messageId?: string;
  children: ReactNode;
}

/**
 * Label + control + error/helper wrapper (MDS Connect `label.f`).
 * Use it around any control; `Input` already uses it internally.
 *
 * @example
 * <Field label="Майстер" htmlFor="master" required error={errors.master}>
 *   <select id="master">…</select>
 * </Field>
 */
export function Field({
  label,
  htmlFor,
  required = false,
  error,
  helper,
  messageId,
  className,
  children,
  ...rest
}: FieldProps) {
  const message = error || helper;
  return (
    <div className={cn('flex min-w-0 flex-col gap-1.5', className)} {...rest}>
      {label && (
        <label htmlFor={htmlFor} className="text-xs font-medium leading-tight text-ink-2">
          {label}
          {required && (
            <span className="ml-0.5 text-danger" aria-hidden="true">
              *
            </span>
          )}
        </label>
      )}
      {children}
      {message && (
        <p
          id={messageId}
          role={error ? 'alert' : undefined}
          className={cn('text-xs', error ? 'text-danger' : 'text-ink-3')}
        >
          {message}
        </p>
      )}
    </div>
  );
}
