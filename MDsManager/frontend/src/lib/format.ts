const TZ = 'Europe/Kyiv';

export function listTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const key = (x: Date) => x.toLocaleDateString('uk-UA', { timeZone: TZ });
  if (key(d) === key(now)) {
    return d.toLocaleTimeString('uk-UA', { timeZone: TZ, hour: '2-digit', minute: '2-digit' });
  }
  const y = new Date(now);
  y.setDate(now.getDate() - 1);
  if (key(d) === key(y)) return 'Вчора';
  return d.toLocaleDateString('uk-UA', { timeZone: TZ, day: '2-digit', month: '2-digit' });
}

export function msgTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('uk-UA', { timeZone: TZ, hour: '2-digit', minute: '2-digit' });
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join('');
}

export function dayLabel(iso: string): string {
  const key = (x: Date) => x.toLocaleDateString('uk-UA', { timeZone: TZ });
  const d = new Date(iso);
  const now = new Date();
  const y = new Date(now);
  y.setDate(now.getDate() - 1);
  if (key(d) === key(now)) return 'Сьогодні';
  if (key(d) === key(y)) return 'Вчора';
  return d.toLocaleDateString('uk-UA', { timeZone: TZ, day: 'numeric', month: 'long' });
}
