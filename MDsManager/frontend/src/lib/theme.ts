/**
 * Світла / темна тема — як у MDS Connect: <html data-theme="dark">, вибір у localStorage["mds_theme"].
 */
import { useSyncExternalStore } from 'react';

export type Theme = 'light' | 'dark';

const KEY = 'mds_theme';
// колір рядка стану / вкладки — фон сторінки (Connect: setThemeColor)
const THEME_COLOR: Record<Theme, string> = { light: '#f4f3ee', dark: '#0b1a15' };

const listeners = new Set<() => void>();

export function getTheme(): Theme {
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
}

function apply(theme: Theme): void {
  const root = document.documentElement;
  if (theme === 'dark') root.setAttribute('data-theme', 'dark');
  else root.removeAttribute('data-theme');
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_COLOR[theme]);
  listeners.forEach((l) => l());
}

export function setTheme(theme: Theme): void {
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* приватний режим — діє до перезавантаження */
  }
  apply(theme);
}

export function toggleTheme(): void {
  setTheme(getTheme() === 'dark' ? 'light' : 'dark');
}

/** Застосовує збережену тему — викликати до першого рендера (без «спалаху» світлої). */
export function applyStoredTheme(): void {
  let stored: string | null = null;
  try {
    stored = localStorage.getItem(KEY);
  } catch {
    /* ignore */
  }
  apply(stored === 'dark' ? 'dark' : 'light');
}

export function useTheme(): Theme {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    getTheme,
    () => 'light',
  );
}
