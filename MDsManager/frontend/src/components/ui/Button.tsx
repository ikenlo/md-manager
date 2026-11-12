import { Loader2 } from 'lucide-react';
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { cn } from './cn';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'accent';
export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Visual style (MDS Connect `.btn` variants). Defaults to `primary`. */
  variant?: ButtonVariant;
  /** sm 32px · md 40px · lg 48px (Connect `.btn.sm` / `.btn` / `.btn.big`). Defaults to `md`. */
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
  // Connect .btn.primary: зелений градієнт; у темній темі — золото
  primary: cn(
    'border-brand bg-gradient-to-b from-brand-2 to-brand text-white',
    'shadow-[inset_0_1px_0_rgba(255,255,255,.1),0_1px_2px_rgba(20,57,44,.25),0_2px_8px_rgba(20,57,44,.12)]',
    'hover:border-brand-2 hover:from-brand-2 hover:to-brand-2',
    'dark:border-gold dark:from-gold dark:to-gold dark:text-[#17120a] dark:shadow-none dark:hover:border-[#ddb96e] dark:hover:from-[#ddb96e] dark:hover:to-[#ddb96e]',
  ),
  // Connect .btn (базова): біла з рамкою
  secondary: 'border-line-strong bg-surface text-ink shadow-sm hover:border-ink-3 hover:bg-surface-2 dark:shadow-none',
  ghost: 'border-transparent bg-transparent text-ink hover:bg-surface-3',
  danger: 'border-danger/35 bg-transparent text-danger hover:bg-danger-bg',
  accent: 'border-gold bg-gold text-white shadow-sm hover:brightness-105 dark:text-[#17120a]',
};

const SIZES: Record<ButtonSize, string> = {
  sm: 'min-h-8 px-3 text-[13px] gap-1.5 rounded-sm',
  md: 'min-h-10 px-4 text-sm gap-2 rounded-md',
  lg: 'min-h-12 px-6 text-[15px] gap-2 rounded-lg',
};

const SPINNER: Record<ButtonSize, number> = { sm: 14, md: 16, lg: 18 };

/**
 * Button in the MDS Connect style (`.btn`).
 *
 * While `loading`, the label stays in the layout (transparent, still readable by screen readers
 * and `getByRole(..., { name })`) so the width does not jump; a spinner is shown on top and the
 * button is disabled with `aria-busy`.
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
        'relative inline-flex select-none items-center justify-center whitespace-nowrap border font-semibold',
        '[-webkit-tap-highlight-color:transparent] transition duration-1 ease-ease',
        'active:scale-[.97] focus-visible:outline-none focus-visible:shadow-ring',
        'disabled:active:scale-100',
        loading ? 'cursor-wait' : 'disabled:cursor-not-allowed disabled:opacity-45 disabled:shadow-none',
        VARIANTS[variant],
        SIZES[size],
        fullWidth && 'w-full',
        className,
      )}
      {...rest}
    >
      {/* opacity-0, а не visibility:hidden: підпис лишається в дереві доступності (назва кнопки) */}
      <span className={cn('inline-flex items-center gap-[inherit]', loading && 'opacity-0')}>
        {iconLeft}
        {children}
        {iconRight}
      </span>
      {loading && (
        <span className="pointer-events-none absolute inset-0 flex items-center justify-center" aria-hidden="true">
          <Loader2 size={SPINNER[size]} className="animate-spin" />
        </span>
      )}
    </button>
  );
});

/** Square icon-only button (Connect `.icon-btn`): 34px, transparent, subtle hover. Needs `aria-label`. */
export const IconButton = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement>>(function IconButton(
  { className, type = 'button', ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        'grid h-[34px] w-[34px] shrink-0 place-items-center rounded-sm text-current transition duration-1',
        'hover:bg-[rgba(127,127,127,.14)] active:scale-[.94] focus-visible:outline-none focus-visible:shadow-ring',
        'disabled:cursor-not-allowed disabled:opacity-45',
        className,
      )}
      {...rest}
    />
  );
});
