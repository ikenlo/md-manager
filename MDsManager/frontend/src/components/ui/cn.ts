/**
 * Joins class names, skipping falsy values.
 * Minimal replacement for `clsx` — enough for static Tailwind class maps.
 */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}
