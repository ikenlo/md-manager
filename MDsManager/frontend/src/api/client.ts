import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { redirectToLogin } from '../lib/flash';
import { useAuthStore } from '../store/auth';
import { toast } from '../store/toast';
import type { LoginResponse, User } from '../types';

declare module 'axios' {
  interface AxiosRequestConfig {
    /** Caller handles 401/429 itself (login, refresh, logout): no toast, no redirect. */
    skipAuthHandling?: boolean;
    /** Internal: request was already retried with a newer token. */
    _retried?: boolean;
  }
}

/**
 * Empty baseURL = same origin: in dev Vite proxies /api → :8000, in production
 * FastAPI serves the built frontend itself (also behind Cloudflare Tunnel).
 * Set VITE_API_URL only when the API lives on another origin.
 */
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  timeout: 15000,
});

api.interceptors.request.use((cfg) => {
  const { token } = useAuthStore.getState();
  if (token && !cfg.headers.Authorization) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

const bearerOf = (cfg: InternalAxiosRequestConfig | undefined) =>
  String(cfg?.headers?.Authorization ?? '').replace(/^Bearer\s+/i, '');

api.interceptors.response.use(undefined, async (error: AxiosError) => {
  const cfg = error.config;
  const status = error.response?.status;
  if (!cfg || cfg.skipAuthHandling) throw error;

  if (status === 401) {
    // Токен могли щойно оновити (ця чи інша вкладка) — повторюємо один раз із новим
    const current = useAuthStore.getState();
    const sent = bearerOf(cfg);
    if (!cfg._retried && current.isAuthenticated() && current.token && current.token !== sent) {
      cfg._retried = true;
      cfg.headers.Authorization = `Bearer ${current.token}`;
      return api.request(cfg);
    }
    useAuthStore.getState().clearAuth();
    redirectToLogin('Сесія закінчилась. Увійдіть знову.', 'error');
    throw error;
  }
  if (status === 429) toast.error('Забагато спроб. Зачекайте 15 хв.');
  throw error;
});

export async function loginRequest(email: string, password: string): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>(
    '/api/auth/login',
    { email, password },
    { skipAuthHandling: true },
  );
  return data;
}

export async function refreshRequest(token: string): Promise<{ token: string; expires_at: string }> {
  const { data } = await api.post<{ token: string; expires_at: string }>('/api/auth/refresh', null, {
    headers: { Authorization: `Bearer ${token}` },
    skipAuthHandling: true,
  });
  return data;
}

export async function meRequest(): Promise<User> {
  const { data } = await api.get<User>('/api/auth/me');
  return data;
}

/** Revokes the session on the server. Token is passed explicitly: the store may already be cleared. */
export async function logoutRequest(token: string): Promise<void> {
  await api.post('/api/auth/logout', null, {
    headers: { Authorization: `Bearer ${token}` },
    skipAuthHandling: true,
  });
}
