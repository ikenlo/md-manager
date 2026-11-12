import { useAuthStore } from '../store/auth';
import { redirectToLogin } from './flash';

/** Shared across tabs: activity in any tab keeps all tabs signed in. */
const ACTIVITY_KEY = 'mds_last_activity';
const EVENTS = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'] as const;
const THROTTLE_MS = 5_000;
const CHECK_EVERY_MS = 15_000;

let checkTimer: ReturnType<typeof setInterval> | null = null;
let lastLocal = 0;
let lastMark = 0;
let limitMs = 30 * 60_000;

function readShared(): number {
  try {
    return Number(localStorage.getItem(ACTIVITY_KEY)) || 0;
  } catch {
    return 0;
  }
}

function markActivity(): void {
  const now = Date.now();
  if (now - lastMark < THROTTLE_MS) return;
  lastMark = now;
  lastLocal = now;
  try {
    localStorage.setItem(ACTIVITY_KEY, String(now));
  } catch {
    /* ignore */
  }
}

function check(): void {
  if (!useAuthStore.getState().token) return;
  const last = Math.max(lastLocal, readShared());
  if (Date.now() - last < limitMs) return;
  stopIdleTimer();
  useAuthStore.getState().clearAuth();
  redirectToLogin('Ви вийшли через неактивність', 'info');
}

/**
 * Signs out after `minutes` without mouse/keyboard/touch/scroll activity in any tab.
 * Activity is throttled to one write per 5 s. Idempotent.
 */
export function startIdleTimer(minutes = 30): void {
  limitMs = minutes * 60_000;
  if (checkTimer !== null) return;
  lastMark = 0;
  markActivity();
  EVENTS.forEach((ev) => window.addEventListener(ev, markActivity, { passive: true, capture: true }));
  checkTimer = setInterval(check, CHECK_EVERY_MS);
}

export function stopIdleTimer(): void {
  EVENTS.forEach((ev) => window.removeEventListener(ev, markActivity, { capture: true }));
  if (checkTimer !== null) clearInterval(checkTimer);
  checkTimer = null;
}
