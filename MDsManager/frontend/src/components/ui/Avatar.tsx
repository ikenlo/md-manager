import { useEffect, useState, type HTMLAttributes } from 'react';
import { cn } from './cn';

export type AvatarSize = 'sm' | 'md' | 'lg' | 'xl';
export type AvatarStatus = 'online' | 'offline' | 'away';

export interface AvatarProps extends HTMLAttributes<HTMLSpanElement> {
  /** Person's name: used for the fallback letter and the accessible label. */
  name: string;
  /** Photo URL. If missing or it fails to load, the first letter is shown. */
  src?: string;
  /** sm 32px · md 40px · lg 48px · xl 64px. Defaults to `md`. */
  size?: AvatarSize;
  /** Presence dot in the bottom-right corner. */
  status?: AvatarStatus;
}

const SIZES: Record<AvatarSize, string> = {
  sm: 'h-8 w-8 text-base',
  md: 'h-10 w-10 text-xl',
  lg: 'h-12 w-12 text-2xl',
  xl: 'h-16 w-16 text-[32px]',
};

const DOT_SIZES: Record<AvatarSize, string> = {
  sm: 'h-2 w-2',
  md: 'h-2.5 w-2.5',
  lg: 'h-3 w-3',
  xl: 'h-3.5 w-3.5',
};

const STATUS: Record<AvatarStatus, { cls: string; label: string }> = {
  online: { cls: 'bg-ok', label: 'онлайн' },
  offline: { cls: 'bg-ink-3', label: 'офлайн' },
  away: { cls: 'bg-warn', label: 'відійшов' },
};

/**
 * Round avatar: photo, or the first letter of `name` in Cormorant on a gold gradient.
 *
 * @example
 * <Avatar name="Олена Коваль" size="lg" status="online" />
 */
export function Avatar({ name, src, size = 'md', status, className, ...rest }: AvatarProps) {
  const [broken, setBroken] = useState(false);
  useEffect(() => setBroken(false), [src]);

  const letter = name.trim().charAt(0).toUpperCase() || '?';
  const showImg = Boolean(src) && !broken;
  const label = status ? `${name}, ${STATUS[status].label}` : name;

  return (
    <span
      role="img"
      aria-label={label}
      title={name}
      className={cn('relative inline-flex shrink-0', SIZES[size], className)}
      {...rest}
    >
      {showImg ? (
        <img
          src={src}
          alt=""
          onError={() => setBroken(true)}
          className="h-full w-full rounded-full object-cover"
        />
      ) : (
        <span
          aria-hidden="true"
          className="flex h-full w-full items-center justify-center rounded-full bg-gradient-to-br from-gold to-gold-soft font-serif font-semibold leading-none text-brand"
        >
          {letter}
        </span>
      )}
      {status && (
        <span
          aria-hidden="true"
          className={cn(
            'absolute bottom-0 right-0 rounded-full ring-2 ring-surface',
            DOT_SIZES[size],
            STATUS[status].cls,
          )}
        />
      )}
    </span>
  );
}
