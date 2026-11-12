import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from 'react';
import { cn } from './cn';
import { Field } from './Field';

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  /** Text above the input. */
  label?: ReactNode;
  /** Error text; also switches the border to `danger` and sets `aria-invalid`. */
  error?: ReactNode;
  /** Hint text below the input (hidden while `error` is shown). */
  helper?: ReactNode;
  /** Icon inside the input on the left (e.g. `<Search size={16} />`). */
  iconLeft?: ReactNode;
  /** Classes for the outer `Field` wrapper. */
  className?: string;
  /** Classes for the `<input>` element itself. */
  inputClassName?: string;
}

/**
 * Text input in the MDS Connect style: label above, optional icon inside, error/helper below.
 * All standard `<input>` props are forwarded (`type`, `value`, `onChange`, `name`, `autoComplete`, …).
 * Font size is 16px below `md` so iOS Safari does not zoom on focus.
 *
 * @example
 * <Input label="Email" type="email" iconLeft={<Mail size={16} />} value={email}
 *        onChange={(e) => setEmail(e.target.value)} error={err} required />
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, helper, iconLeft, required, disabled, id, className, inputClassName, type = 'text', ...rest },
  ref,
) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const messageId = error || helper ? `${inputId}-msg` : undefined;
  return (
    <Field
      label={label}
      htmlFor={inputId}
      required={required}
      error={error}
      helper={helper}
      messageId={messageId}
      className={className}
    >
      <div className={cn('relative', disabled && 'opacity-50')}>
        {iconLeft && (
          <span className="pointer-events-none absolute left-3 top-1/2 flex -translate-y-1/2 text-ink-3">
            {iconLeft}
          </span>
        )}
        <input
          ref={ref}
          id={inputId}
          type={type}
          required={required}
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={messageId}
          className={cn(
            'h-10 w-full rounded-md border bg-surface px-3 text-base text-ink outline-none md:text-sm',
            'transition duration-1 ease-ease placeholder:text-ink-3',
            'disabled:cursor-not-allowed disabled:bg-surface-2',
            error
              ? 'border-danger focus:ring-2 focus:ring-danger/20'
              : 'border-line-strong hover:border-ink-3 focus:border-brand focus:ring-2 focus:ring-brand/20 disabled:hover:border-line-strong',
            iconLeft ? 'pl-9' : undefined,
            inputClassName,
          )}
          {...rest}
        />
      </div>
    </Field>
  );
});
