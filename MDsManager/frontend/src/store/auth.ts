import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import type { User } from '../types';

/** localStorage key; other tabs listen to it (see lib/refresh.ts → startAuthSync). */
export const AUTH_STORAGE_KEY = 'mds_auth';

interface AuthState {
  token: string | null;
  user: User | null;
  /** Session end, ms since epoch (UTC). */
  expiresAt: number | null;
  /** Dev-only offline demo login (no backend): no refresh, no API calls. */
  isMock: boolean;
  setAuth: (token: string, user: User, expiresAt: number, isMock?: boolean) => void;
  setUser: (user: User) => void;
  clearAuth: () => void;
  /** Token present and not expired. */
  isAuthenticated: () => boolean;
}

/** Pure check, usable in selectors: `useAuthStore(selectIsAuthenticated)`. */
export const selectIsAuthenticated = (s: Pick<AuthState, 'token' | 'expiresAt'>): boolean =>
  Boolean(s.token) && s.expiresAt !== null && s.expiresAt > Date.now();

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      expiresAt: null,
      isMock: false,
      setAuth: (token, user, expiresAt, isMock = false) => set({ token, user, expiresAt, isMock }),
      setUser: (user) => set({ user }),
      clearAuth: () => set({ token: null, user: null, expiresAt: null, isMock: false }),
      isAuthenticated: () => selectIsAuthenticated(get()),
    }),
    {
      name: AUTH_STORAGE_KEY,
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ token: s.token, user: s.user, expiresAt: s.expiresAt, isMock: s.isMock }),
    },
  ),
);

/** Parses the backend's ISO datetime; a value without a zone is treated as UTC. */
export function parseExpiry(iso: string): number {
  const hasZone = /(Z|[+-]\d\d:?\d\d)$/.test(iso);
  return Date.parse(hasZone ? iso : `${iso}Z`);
}

// Ключі попередньої версії входу — прибираємо, щоб не лишався старий токен
try {
  localStorage.removeItem('mds.token');
  localStorage.removeItem('mds.user');
} catch {
  /* private mode */
}
