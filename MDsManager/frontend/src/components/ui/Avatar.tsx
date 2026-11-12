import { useEffect, useState, type HTMLAttributes } from 'react';
import { cn } from './cn';

export type AvatarSize = 'sm' | 'md' | 'lg' | 'xl';
export type AvatarStatus = 'online' | 'offline' | 'away';

export interface AvatarProps extends HTMLAttributes<HTMLSpanElement> {
  /** Person's name: initials, colour and accessible label. */
  name: string;
  /** Photo URL. If missing or it fails to load, initials are shown. */
  src?: string;
  /** sm 26px · md 34px · lg 46px · xl 64px (Connect `.avatar.sm / .avatar / .avatar.lg`). Defaults to `md`. */
  size?: AvatarSize;
  /** Presence dot in the bottom-right corner. */
  status?: AvatarStatus;
}

// Connect AV_COLORS: колір — стабільний хеш імені, тож людина завжди одного кольору
const COLORS = ['#1d4d3b', '#8a6a2f', '#3f5a7a', '#7a4a5c', '#4f6b3a', '#5b4a7a', '#2f6b6b', '#7a5a3a'];

export function avatarColor(name: string): string {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return COLORS[h % COLORS.length]!;
}

export function initials(name: string): string {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((w) => w[0]!.toUpperCase())
      .join('') || '?'
  );
}

const SIZES: Record<AvatarSize, string> = {
  sm: 'h-[26px] w-[26px] text-2xs',
  md: 'h-[34px] w-[34px] text-[13px]',
  lg: 'h-[46px] w-[46px] text-base',
  xl: 'h-16 w-16 text-xl',
};

const DOT: Record<AvatarSize, string> = { sm: 'h-2 w-2', md: 'h-2.5 w-2.5', lg: 'h-3 w-3', xl: 'h-3.5 w-3.5' };

const STATUS: Record<AvatarStatus, { cls: string; label: string }> = {
  online: { cls: 'bg-ok', label: 'онлайн' },
  offline: { cls: 'bg-ink-3', label: 'офлайн' },
  away: { cls: 'bg-warn', label: 'відійшов' },
};

/** Round avatar (MDS Connect `.avatar`): photo, or initials on a muted colour derived from the name. */
export function Avatar({ name, src, size = 'md', status, className, ...rest }: AvatarProps) {
  const [broken, setBroken] = useState(false);
  useEffect(() => setBroken(false), [src]);
  const showImg = Boolean(src) && !broken;
  const label = status ? `${name}, ${STATUS[status].label}` : name;

  return (
    <span role="img" aria-label={label} title={name} className={cn('relative inline-flex shrink-0', SIZES[size], className)} {...rest}>
      {showImg ? (
        <img src={src} alt="" onError={() => setBroken(true)} className="h-full w-full rounded-full object-cover" />
      ) : (
        <span
          aria-hidden="true"
          style={{ background: avatarColor(name) }}
          className="flex h-full w-full items-center justify-center rounded-full font-bold leading-none text-white"
        >
          {initials(name)}
        </span>
      )}
      {status && (
        <span aria-hidden="true" className={cn('absolute bottom-0 right-0 rounded-full ring-2 ring-surface', DOT[size], STATUS[status].cls)} />
      )}
    </span>
  );
}
