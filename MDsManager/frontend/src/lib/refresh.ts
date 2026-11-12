import axios from 'axios';
import { refreshRequest } from '../api/client';
import { AUTH_STORAGE_KEY, parseExpiry, useAuthStore } from '../store/auth';
import { redirectToLogin } from './flash';

const LOCK_KEY = 'mds_refresh_lock';
const LOCK_TTL_MS = 30_000;
const CHECK_EVERY_MS = 60_000;
/** Refresh when less than this is left. */
const REFRESH_BEFORE_MS = 5 * 60_000;

const TAB_ID = Math.random().toString(36).slice(2) + Date.now().toString(36);

let timer: ReturnType<typeof setInterval> | null = null;
let inFlight = false;

type Lock = { timestamp: number; tabId: string };

function readLock(): Lock | null {
  try {
    const raw = localStorage.getItem(LOCK_KEY);
    return raw ? (JSON.parse(raw) as Lock) : null;
  } catch {
    return null;
  }
}

/**
 * Best-effort cross-tab mutex: write our id, then read back — if another tab
 * wrote in between, it wins. Stale locks (> 30 s, e.g. a tab closed mid-refresh) are ignored.
 */
function acquireLock(): boolean {
  const lock = readLock();
  if (lock && lock.tabId !== TAB_ID && Date.now() - lock.timestamp < LOCK_TTL_MS) return false;
  try {
    localStorage.setItem(LOCK_KEY, JSON.stringify({ timestamp: Date.now(), tabId: TAB_ID }));
  } catch {
    return true; // storage unavailable — single tab anyway
  }
  return readLock()?.tabId === TAB_ID;
}

function releaseLock(): void {
  if (readLock()?.tabId === TAB_ID) {
    try {
      localStorage.removeItem(LOCK_KEY);
    } catch {
      /* ignore */
    }
  }
}

/** Refreshes the token if it expires within 5 minutes. Safe to call often and from several tabs. */
export async function refreshIfNeeded(force = false): Promise<void> {
  if (inFlight) return;
  // Інша вкладка могла вже оновити токен — беремо свіжий стан зі сховища
  await useAuthStore.persist.rehydrate();
  const { token, expiresAt, isMock } = useAuthStore.getState();
  if (!token || !expiresAt || isMock) return;
  const left = expiresAt - Date.now();
  if (left <= 0) {
    useAuthStore.getState().clearAuth();
    redirectToLogin('Сесія закінчилась. Увійдіть знову.', 'error');
    return;
  }
  if (!force && left > REFRESH_BEFORE_MS) return;
  if (!acquireLock()) return;

  inFlight = true;
  try {
    const res = await refreshRequest(token);
    const { user } = useAuthStore.getState();
    if (user) useAuthStore.getState().setAuth(res.token, user, parseExpiry(res.expires_at));
  } catch (err) {
    if (axios.isAxiosError(err) && err.response?.status === 401) {
      useAuthStore.getState().clearAuth();
      redirectToLogin('Сесія закінчилась. Увійдіть знову.', 'error');
    }
    // мережа/5xx — спробуємо на наступній перевірці
  } finally {
    inFlight = false;
    releaseLock();
  }
}

/** Checks every 60 s whether the token needs a refresh. Idempotent. */
export function startRefreshTimer(): void {
  if (timer !== null) return;
  timer = setInterval(() => void refreshIfNeeded(), CHECK_EVERY_MS);
  void refreshIfNeeded();
}

export function stopRefreshTimer(): void {
  if (timer !== null) clearInterval(timer);
  timer = null;
}

/**
 * Keeps this tab's auth store in sync with other tabs (login, refresh, logout).
 * Returns an unsubscribe function.
 */
export function startAuthSync(): () => void {
  const onStorage = (e: StorageEvent) => {
    if (e.key !== AUTH_STORAGE_KEY && e.key !== null) return; // null = localStorage.clear()
    if (e.newValue === null) useAuthStore.getState().clearAuth();
    else void useAuthStore.persist.rehydrate();
  };
  window.addEventListener('storage', onStorage);
  return () => window.removeEventListener('storage', onStorage);
}
