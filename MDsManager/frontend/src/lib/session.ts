import { logoutRequest } from '../api/client';
import { useAuthStore } from '../store/auth';
import { redirectToLogin } from './flash';
import { stopIdleTimer } from './idle';
import { stopRefreshTimer } from './refresh';
import { disconnect as disconnectWs } from './ws';

/** Manual logout: revoke on the server (fire and forget), clear everything, go to /login. */
export function logout(): void {
  const { token, isMock } = useAuthStore.getState();
  if (token && !isMock) logoutRequest(token).catch(() => undefined);
  disconnectWs();
  stopRefreshTimer();
  stopIdleTimer();
  useAuthStore.getState().clearAuth();
  redirectToLogin('Ви вийшли', 'success');
}
