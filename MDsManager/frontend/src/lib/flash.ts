import { toast } from '../store/toast';

const FLASH_KEY = 'mds_flash';
type FlashType = 'success' | 'error' | 'warning' | 'info';

let redirecting = false;

/**
 * Full-page redirect to /login. The toast is stashed in sessionStorage and shown
 * after the reload by `showFlash()`, otherwise it would vanish with the page.
 * Repeated calls (several 401s at once) are ignored.
 */
export function redirectToLogin(message?: string, type: FlashType = 'info'): void {
  if (redirecting) return;
  redirecting = true;
  if (message) {
    try {
      sessionStorage.setItem(FLASH_KEY, JSON.stringify({ type, message }));
    } catch {
      /* private mode — toast is lost, redirect still happens */
    }
  }
  window.location.href = '/login';
}

/** Shows a toast saved by `redirectToLogin` before the reload. Call once on app start. */
export function showFlash(): void {
  try {
    const raw = sessionStorage.getItem(FLASH_KEY);
    if (!raw) return;
    sessionStorage.removeItem(FLASH_KEY);
    const { type, message } = JSON.parse(raw) as { type: FlashType; message: string };
    toast[type](message);
  } catch {
    /* ignore malformed */
  }
}
