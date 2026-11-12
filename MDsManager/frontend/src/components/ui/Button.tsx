import { Loader2 } from 'lucide-react';
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { cn } from './cn';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Visual style. Defaults to `primary`. */
  variant?: ButtonVariant;
  /** Height / padding / font size. Defaults to `md`. */
  size?: ButtonSize;
  /** Shows a spinner instead of the label and blocks clicks. */
  loading?: boolean;
  /** Icon rendered before the label (e.g. `<Send size={16} />`). */
  iconLeft?: ReactNode;
  /** Icon rendered after the label. */
  iconRight?: ReactNode;
  /** Stretches the button to the container width. */
  fullWidth?: boolean;
}

const VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-brand text-brand-ink border border-brand shadow-sm hover:bg-brand-2 hover:border-brand-2',
  secondary: 'bg-surface-2 text-ink border border-line hover:border-line-strong hover:bg-surface-3',
  ghost: 'bg-transparent text-ink border border-transparent hover:bg-surface-2',
  danger: 'bg-danger text-white border border-danger shadow-sm hover:brightness-95',
};

const SIZES: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-xs gap-1.5 rounded-sm',
  md: 'h-10 px-4 text-sm gap-2 rounded-md',
  lg: 'h-12 px-6 text-base gap-2 rounded-lg',
};

const SPINNER: Record<ButtonSize, number> = { sm: 14, md: 16, lg: 18 };

/**
 * Button in the MDS Connect style (`.btn`).
 *
 * While `loading`, the label stays in the layout (invisible) so the width does not jump,
 * a spinner is shown on top and the button is disabled with `aria-busy`.
 *
 * @example
 * <Button iconLeft={<Send size={16} />} loading={saving} onClick={save}>Надіслати</Button>
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'primary',
    size = 'md',
    loading = false,
    iconLeft,
    iconRight,
    fullWidth = false,
    disabled,
    type = 'button',
    className,
    children,
    ...rest
  },
  ref,
) {
  const inactive = disabled || loading;
  return (
    <button
      ref={ref}
      type={type}
      disabled={inactive}
      aria-busy={loading || undefined}
      className={cn(
        'relative inline-flex select-none items-center justify-center whitespace-nowrap font-semibold',
        'transition duration-1 ease-ease active:scale-[.97] focus-visible:outline-none focus-visible:shadow-ring',
        'disabled:active:scale-100',
        loading ? 'cursor-wait' : 'disabled:cursor-not-allowed disabled:opacity-50',
        VARIANTS[variant],
        SIZES[size],
        fullWidth && 'w-full',
        className,
      )}
      {...rest}
    >
      <span className={cn('inline-flex items-center gap-[inherit]', loading && 'invisible')}>
        {iconLeft}
        {children}
        {iconRight}
      </span>
      {loading && (
        <span className="absolute inset-0 flex items-center justify-center">
          <Loader2 size={SPINNER[size]} className="animate-spin" aria-hidden="true" />
        </span>
      )}
    </button>
  );
});
