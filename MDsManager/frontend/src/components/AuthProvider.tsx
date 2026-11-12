import { useEffect, type ReactNode } from 'react';
import { meRequest } from '../api/client';
import { showFlash } from '../lib/flash';
import { startIdleTimer, stopIdleTimer } from '../lib/idle';
import { startAuthSync, startRefreshTimer, stopRefreshTimer } from '../lib/refresh';
import { selectIsAuthenticated, useAuthStore } from '../store/auth';

const IDLE_MINUTES = Number(import.meta.env.VITE_IDLE_MINUTES) || 30;

/**
 * Session lifecycle: cross-tab sync, silent token refresh, idle logout,
 * and a `/me` check on start (a revoked token → 401 → /login).
 */
export default function AuthProvider({ children }: { children: ReactNode }) {
  const authed = useAuthStore(selectIsAuthenticated);
  const isMock = useAuthStore((s) => s.isMock);

  useEffect(() => {
    showFlash();
    return startAuthSync();
  }, []);

  useEffect(() => {
    if (!authed) return;
    startIdleTimer(IDLE_MINUTES);
    if (!isMock) startRefreshTimer();
    return () => {
      stopRefreshTimer();
      stopIdleTimer();
    };
  }, [authed, isMock]);

  // Перевірка сесії при старті / після входу в іншій вкладці
  useEffect(() => {
    if (!authed || isMock) return;
    meRequest()
      .then((u) => useAuthStore.getState().setUser(u))
      .catch(() => undefined); // 401 обробляє інтерсептор
  }, [authed, isMock]);

  return <>{children}</>;
}
